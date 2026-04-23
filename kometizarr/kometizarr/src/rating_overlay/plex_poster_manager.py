"""
Plex Poster Manager - Apply rating overlays to Plex library

Integrates all components: backup, rating fetch, overlay, upload
MIT License - Copyright (c) 2026 Kometizarr Contributors
"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
from plexapi.server import PlexServer
from plexapi.library import LibrarySection

from .backup_manager import PosterBackupManager
from .rating_fetcher import RatingFetcher
from .badge_generator import BadgeGenerator
from .overlay_composer import OverlayComposer
from .multi_rating_badge import MultiRatingBadge
from .vmgr_fetcher import VMGRFetcher
from ..utils.logger import ProgressTracker, print_header, print_subheader, print_summary

logger = logging.getLogger(__name__)


class PlexPosterManager:
    """Apply rating overlays to Plex posters with automatic backup"""

    def __init__(
        self,
        plex_url: str,
        plex_token: str,
        library_name: str,
        tmdb_api_key: str,
        omdb_api_key: Optional[str] = None,
        mdblist_api_key: Optional[str] = None,
        backup_dir: str = './data/kometizarr_backups',
        badge_style: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        rating_sources: Optional[Dict[str, bool]] = None,
        vmgr_db_url: Optional[str] = None
    ):
        """
        Initialize Plex poster manager

        Args:
            plex_url: Plex server URL
            plex_token: Plex authentication token
            library_name: Library name (e.g., 'Movies')
            tmdb_api_key: TMDB API key
            omdb_api_key: Optional OMDb API key
            backup_dir: Directory for poster backups
            badge_style: Optional dict with styling options (size, font, color, opacity)
            dry_run: If True, preview operations without applying
            rating_sources: Optional dict to control which ratings to show
                           e.g. {'tmdb': True, 'imdb': True, 'rt_critic': False, 'rt_audience': False,
                                 'vmgr_score': True, 'resolution_4k': True}
                           If None, shows all available ratings
            vmgr_db_url: Optional PostgreSQL DSN for VideoManager score lookup
                         e.g. 'postgresql://postgres:password@localhost:5433/video_manager'
        """
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.library_name = library_name
        self.dry_run = dry_run
        self.rating_sources = rating_sources or {}
        self.badge_style = badge_style or {}  # Store badge styling options

        # Connect to Plex
        self.server = PlexServer(plex_url, plex_token)
        self.library = self.server.library.section(library_name)

        # Initialize components
        self.backup_manager = PosterBackupManager(backup_dir)
        self.rating_fetcher = RatingFetcher(tmdb_api_key, omdb_api_key, mdblist_api_key)
        # BadgeGenerator is legacy (old unified badge), badge_style is now a dict for MultiRatingBadge
        self.badge_generator = BadgeGenerator(style='default')
        self.overlay_composer = OverlayComposer(self.badge_generator)
        self.multi_rating_badge = MultiRatingBadge()  # New multi-source badge (uses badge_style dict)

        # Optional VideoManager score fetcher
        self.vmgr_fetcher: Optional[VMGRFetcher] = VMGRFetcher(vmgr_db_url) if vmgr_db_url else None

        # Temp directory for processing
        self.temp_dir = Path('/tmp/kometizarr_temp')
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Connected to Plex: {self.server.friendlyName}")
        logger.info(f"Library: {library_name} ({len(self.library.all())} items)")
        if dry_run:
            logger.info("DRY-RUN MODE: No changes will be applied")
        if self.vmgr_fetcher:
            logger.info("VideoManager DB: connected for quality score lookup")

    def _extract_tmdb_id(self, guids: list) -> Optional[int]:
        """Extract TMDB ID from Plex GUIDs"""
        for guid in guids:
            if 'tmdb://' in guid.id:
                return int(guid.id.split('tmdb://')[1])
        return None

    def _extract_imdb_id(self, guids: list) -> Optional[str]:
        """Extract IMDb ID from Plex GUIDs"""
        for guid in guids:
            if 'imdb://' in guid.id:
                return guid.id.split('imdb://')[1]
        return None

    def _extract_plex_ratings(self, movie) -> Dict[str, float]:
        """
        Extract ratings from Plex's own metadata

        Plex stores ratings from multiple sources in the ratings array:
        - TMDB (audience, 0-10 scale)
        - IMDb (audience, 0-10 scale)
        - RT Critic (critic, 0-10 scale -> multiply by 10 for %)
        - RT Audience (audience, 0-10 scale -> multiply by 10 for %)

        Returns:
            Dict with available ratings: {'tmdb': 7.5, 'imdb': 6.8, 'rt_critic': 30.0, 'rt_audience': 92.0}
        """
        plex_ratings = {}

        if hasattr(movie, 'ratings'):
            for rating in movie.ratings:
                rating_type = rating.type
                rating_value = rating.value
                rating_image = rating.image if hasattr(rating, 'image') else ''

                # RT Critic (critic type with RT image)
                if rating_type == 'critic' and 'rottentomatoes' in rating_image:
                    plex_ratings['rt_critic'] = rating_value * 10  # Convert 0-10 to 0-100%

                # RT Audience (audience type with RT image)
                elif rating_type == 'audience' and 'rottentomatoes' in rating_image:
                    plex_ratings['rt_audience'] = rating_value * 10  # Convert 0-10 to 0-100%

                # IMDb (audience type with imdb image)
                elif rating_type == 'audience' and 'imdb' in rating_image:
                    plex_ratings['imdb'] = rating_value

                # TMDB (audience type with themoviedb image)
                elif rating_type == 'audience' and 'themoviedb' in rating_image:
                    plex_ratings['tmdb'] = rating_value

        return plex_ratings

    def process_movie(
        self,
        movie,
        position: str = 'northwest',
        force: bool = False,
        badge_positions: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Optional[bool]:
        """
        Process a single movie: backup, overlay, upload

        Args:
            movie: PlexAPI movie object
            position: Badge position ('northeast', 'northwest', etc.) - legacy unified mode
            force: Force reprocessing even if already has overlay
            badge_positions: Optional dict for individual badge positions
                           {'tmdb': {'x': 5, 'y': 5}, 'imdb': {'x': 20, 'y': 5}, ...}

        Returns:
            True if successfully processed
            None if skipped (already has overlay)
            False if failed
        """
        try:
            # Extract IDs - TMDB ID is optional (many TV shows don't have it)
            tmdb_id = self._extract_tmdb_id(movie.guids)
            imdb_id = self._extract_imdb_id(movie.guids)

            # Need at least one ID to proceed
            if not tmdb_id and not imdb_id:
                logger.warning(f"⚠️  {movie.title}: No TMDB or IMDb ID found")
                return False

            # Skip if overlay already applied (unless force=True)
            if not force and self.backup_manager.has_overlay(self.library_name, movie.title, year=movie.year):
                logger.debug(f"⏭️  {movie.title}: Already has overlay, skipping")
                return None  # Return None to indicate skip (not success or failure)

            # PRIORITY 1: Try to get ALL ratings from Plex's own metadata FIRST (fastest, most reliable)
            # This works for both movies AND TV shows and has ~100% coverage
            plex_ratings = self._extract_plex_ratings(movie)

            # Build ratings dict - start with what Plex has
            ratings = {}

            # Use Plex's TMDB rating if available
            if 'tmdb' in plex_ratings:
                ratings['tmdb'] = plex_ratings['tmdb']
            elif tmdb_id:  # Only try TMDB API if we have a TMDB ID
                # PRIORITY 2: Fall back to TMDB API only if Plex doesn't have it
                # Determine media type (movie vs TV show)
                media_type = 'tv' if self.library.type == 'show' else 'movie'
                rating_data = self.rating_fetcher.fetch_tmdb_rating(tmdb_id, media_type=media_type)

                if rating_data and rating_data.get('rating', 0) > 0:
                    ratings['tmdb'] = rating_data['rating']
                # Don't fail here - continue to check other rating sources

            # Use Plex's IMDb rating if available
            if 'imdb' in plex_ratings:
                ratings['imdb'] = plex_ratings['imdb']

            # Use Plex's RT scores if available
            if 'rt_critic' in plex_ratings:
                ratings['rt_critic'] = plex_ratings['rt_critic']
            if 'rt_audience' in plex_ratings:
                ratings['rt_audience'] = plex_ratings['rt_audience']

            # PRIORITY 2: Fall back to API calls for missing ratings (already extracted imdb_id above)
            if imdb_id:
                # Get IMDb rating from OMDb if not already from Plex
                if 'imdb' not in ratings:
                    imdb_data = self.rating_fetcher.fetch_omdb_rating(imdb_id)
                    if imdb_data and imdb_data.get('imdb_rating'):
                        try:
                            ratings['imdb'] = float(imdb_data['imdb_rating'])
                        except:
                            pass

                # Get RT scores from MDBList if not already from Plex
                if 'rt_critic' not in ratings or 'rt_audience' not in ratings:
                    mdb_data = self.rating_fetcher.fetch_mdblist_rating(imdb_id)
                    if mdb_data:
                        if 'rt_critic' not in ratings and mdb_data.get('rt_critic'):
                            ratings['rt_critic'] = mdb_data['rt_critic']
                        if 'rt_audience' not in ratings and mdb_data.get('rt_audience'):
                            ratings['rt_audience'] = mdb_data['rt_audience']

            # Filter ratings based on user preferences (if specified)
            if self.rating_sources:
                ratings = {
                    k: v for k, v in ratings.items()
                    if self.rating_sources.get(k, True)  # Default to True if not specified
                }

            # ---- Custom badges ----

            # VideoManager quality score
            want_vmgr = self.rating_sources.get('vmgr_score', False) if self.rating_sources else False
            if want_vmgr and self.vmgr_fetcher:
                try:
                    filepath = movie.media[0].parts[0].file if (
                        hasattr(movie, 'media') and movie.media and movie.media[0].parts
                    ) else None
                    if filepath:
                        score = self.vmgr_fetcher.get_quality_score(filepath)
                        if score is not None:
                            ratings['vmgr_score'] = score
                            logger.info(f"VMGR score for {movie.title}: {score}")
                        else:
                            logger.warning(f"⚠️  VMGR: no score found for '{movie.title}' (file: {filepath})")
                except Exception as e:
                    logger.warning(f"⚠️  VMGR lookup failed for {movie.title}: {e}")

            # 4K chip — detect from Plex media info
            want_4k = self.rating_sources.get('resolution_4k', False) if self.rating_sources else False
            if want_4k:
                try:
                    if hasattr(movie, 'media') and movie.media:
                        video_res = str(getattr(movie.media[0], 'videoResolution', '') or '').lower()
                        if '4k' in video_res or video_res == '2160':
                            ratings['resolution_4k'] = 1  # sentinel: 1 = is 4K
                except Exception as e:
                    logger.debug(f"4K check failed for {movie.title}: {e}")

            # Check if we have ANY ratings - fail only if all sources are empty/zero
            if not ratings or all(v == 0 for v in ratings.values()):
                logger.warning(f"⚠️  {movie.title}: No ratings available from any source")
                return False

            logger.info(f"Processing: {movie.title} (Ratings: {ratings})")

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would apply multi-rating overlay to '{movie.title}': {ratings}")
                return True

            # Get poster URL
            poster_url = movie.posterUrl
            if not poster_url:
                logger.warning(f"⚠️  {movie.title}: No poster URL")
                return False

            # Backup original poster
            metadata = {
                'rating_key': movie.ratingKey,
                'tmdb_id': tmdb_id,
                'imdb_id': imdb_id,
                'title': movie.title,
                'year': movie.year,
                'ratings': ratings
            }

            # Get or create backup (never re-download if backup exists)
            # When force=True, we just use existing backup to apply fresh overlay
            original_path = self.backup_manager.backup_poster(
                library_name=self.library_name,
                item_title=movie.title,
                poster_url=poster_url,
                item_metadata=metadata,
                plex_token=self.plex_token,
                force=False,  # Never re-download - use existing backup
                year=movie.year
            )

            if not original_path:
                logger.error(f"✗ {movie.title}: Failed to backup poster")
                return False

            # Apply multi-rating overlay
            overlay_path = self.temp_dir / f"{movie.ratingKey}_overlay.jpg"
            self.multi_rating_badge.apply_to_poster(
                poster_path=str(original_path),
                ratings=ratings,
                output_path=str(overlay_path),
                position=position,
                badge_style=self.badge_style,  # Pass custom styling options
                badge_positions=badge_positions  # Pass individual badge positions if provided
            )

            # Save overlay version to backup
            self.backup_manager.save_overlay_poster(
                library_name=self.library_name,
                item_title=movie.title,
                overlay_image_path=str(overlay_path),
                year=movie.year
            )

            # Upload to Plex
            movie.uploadPoster(filepath=str(overlay_path))
            rating_str = ', '.join([f'{k.upper()}: {v:.1f}' for k, v in ratings.items()])
            logger.info(f"✓ {movie.title}: Multi-rating overlay applied ({rating_str})")

            # Cleanup temp file
            overlay_path.unlink()

            return True

        except Exception as e:
            logger.error(f"✗ {movie.title}: Error - {e}")
            return False

    def process_episode(
        self,
        episode,
        force: bool = False,
        badge_positions: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Optional[bool]:
        """
        Apply VM score + 4K chip onto a single episode thumbnail.

        Series-level ratings (TMDB, IMDb, RT) are deliberately excluded — they
        are identical for every episode and belong on the show/season poster.
        Only ``vmgr_score`` and ``resolution_4k`` are applied.

        Args:
            episode: PlexAPI Episode object
            force: Re-process even if already overlaid
            badge_positions: Optional per-badge position overrides

        Returns:
            True  – overlay applied successfully
            None  – skipped (already has overlay, or no badges to apply)
            False – failed
        """
        show_title = episode.grandparentTitle
        season_number = episode.parentIndex or 0
        ep_index = episode.index or 0
        ep_label = f"{show_title} – S{season_number:02d}E{ep_index:02d}"

        try:
            # Skip if already processed (unless force)
            if not force and self.backup_manager.has_episode_overlay(
                self.library_name, show_title, season_number, ep_index
            ):
                logger.debug(f"⏭️  {ep_label}: Already has overlay, skipping")
                return None

            # Build the (small) ratings dict — episode-specific badges only
            ratings = {}

            want_vmgr = self.rating_sources.get('vmgr_score', False) if self.rating_sources else False
            if want_vmgr and self.vmgr_fetcher:
                try:
                    filepath = (
                        episode.media[0].parts[0].file
                        if (hasattr(episode, 'media') and episode.media and episode.media[0].parts)
                        else None
                    )
                    if filepath:
                        score = self.vmgr_fetcher.get_quality_score(filepath)
                        if score is not None:
                            ratings['vmgr_score'] = score
                        else:
                            logger.warning(f"⚠️  VMGR: no score for '{ep_label}' ({filepath})")
                except Exception as e:
                    logger.warning(f"⚠️  VMGR lookup failed for {ep_label}: {e}")

            want_4k = self.rating_sources.get('resolution_4k', False) if self.rating_sources else False
            if want_4k:
                try:
                    if hasattr(episode, 'media') and episode.media:
                        video_res = str(getattr(episode.media[0], 'videoResolution', '') or '').lower()
                        if '4k' in video_res or video_res == '2160':
                            ratings['resolution_4k'] = 1
                except Exception as e:
                    logger.debug(f"4K check failed for {ep_label}: {e}")

            if not ratings:
                logger.debug(f"⏭️  {ep_label}: No applicable badges, skipping")
                return None

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would apply {list(ratings.keys())} to '{ep_label}'")
                return True

            thumb_url = episode.thumbUrl
            if not thumb_url:
                logger.warning(f"⚠️  {ep_label}: No thumbnail URL")
                return False

            # Backup original thumbnail (no-op if already backed up)
            original_path = self.backup_manager.backup_episode_thumb(
                library_name=self.library_name,
                show_title=show_title,
                season_number=season_number,
                episode_index=ep_index,
                thumb_url=thumb_url,
                plex_token=self.plex_token,
                metadata={
                    'rating_key': episode.ratingKey,
                    'episode': ep_label,
                    'badges': list(ratings.keys()),
                },
            )

            if not original_path:
                logger.error(f"✗ {ep_label}: Failed to backup thumbnail")
                return False

            # Episode thumbnails are landscape (16:9) while movie posters are portrait (2:3).
            # Badge sizing uses poster_width * badge_size_percent, which on a wide image
            # produces a badge that is too tall relative to the short image height.
            # Also, badge_positions from the UI (configured on portrait posters) may place
            # badges at a y% that clips the bottom of a landscape thumbnail.
            #
            # Fix: read the actual thumbnail dimensions, cap badge_size_percent so the badge
            # height never exceeds 22% of the image height, and always anchor at top-left.
            from PIL import Image as _PILImage
            with _PILImage.open(str(original_path)) as _img:
                _thumb_w, _thumb_h = _img.size

            # badge_height = badge_width * 1.4 = (thumb_w * size_pct/100) * 1.4
            # We want badge_height ≤ thumb_h * 0.22  →  size_pct ≤ thumb_h * 22 / (thumb_w * 1.4)
            _max_size_pct = (_thumb_h * 22) / (_thumb_w * 1.4)  # percent of poster_width
            _default_size_pct = (self.badge_style or {}).get('individual_badge_size', 12)
            _ep_size_pct = min(_default_size_pct, _max_size_pct)
            _ep_badge_style = {**(self.badge_style or {}), 'individual_badge_size': _ep_size_pct}

            # Build safe episode-specific badge_positions anchored to the top-left.
            # Each badge is placed in a horizontal row with a small gap between them.
            _margin_x = 2  # % from left edge
            _margin_y = 2  # % from top edge
            _ep_badge_positions = {}
            _x_cursor = _margin_x
            for _src in ratings:
                _ep_badge_positions[_src] = {'x': _x_cursor, 'y': _margin_y}
                # Advance x by badge_width% + a 1% gap so badges don't overlap
                _badge_w_px = int(_thumb_w * _ep_size_pct / 100)
                _x_cursor += int(_badge_w_px / _thumb_w * 100) + 1

            # Apply overlay
            overlay_path = self.temp_dir / f"{episode.ratingKey}_ep_overlay.jpg"
            self.multi_rating_badge.apply_to_poster(
                poster_path=str(original_path),
                ratings=ratings,
                output_path=str(overlay_path),
                position='northwest',
                badge_style=_ep_badge_style,
                badge_positions=_ep_badge_positions,
            )

            # Persist overlay copy
            self.backup_manager.save_episode_overlay(
                library_name=self.library_name,
                show_title=show_title,
                season_number=season_number,
                episode_index=ep_index,
                overlay_image_path=str(overlay_path),
            )

            # Upload to Plex
            episode.uploadPoster(filepath=str(overlay_path))
            logger.info(f"✓ {ep_label}: overlay applied ({', '.join(ratings.keys())})")

            overlay_path.unlink()
            return True

        except Exception as e:
            logger.error(f"✗ {ep_label}: Error – {e}")
            return False

    def process_library(
        self,
        limit: Optional[int] = None,
        position: str = 'northwest',
        force: bool = False,
        rate_limit: float = 0.3
    ) -> Dict[str, int]:
        """
        Process entire library with rating overlays

        Args:
            limit: Max number of movies to process (None = all)
            position: Badge position
            force: Force reprocessing
            rate_limit: Delay between requests (seconds)

        Returns:
            Dict with statistics
        """
        all_movies = self.library.all()
        total = len(all_movies)

        if limit:
            all_movies = all_movies[:limit]
            print_header(f"Processing {limit} of {total} Movies")
        else:
            print_header(f"Processing All {total} Movies")

        # Initialize progress tracker
        progress = ProgressTracker(len(all_movies), "Applying rating overlays")
        start_time = time.time()

        print(f"Library: {self.library_name}")
        print(f"Backup Dir: {self.backup_manager.backup_dir}")
        print(f"Position: {position}")
        print(f"Force Reprocess: {force}")
        print()

        for i, movie in enumerate(all_movies, 1):
            # Show progress
            print_subheader(f"{progress.get_progress_str()} | {movie.title}")

            result = self.process_movie(movie, position=position, force=force)

            # Update progress based on result
            if result is None:
                # None = skipped (already has overlay)
                progress.update(skipped=True)
            elif result:
                # True = success
                progress.update(success=True)
            else:
                # False = failed
                progress.update(success=False)

            # Show current stats
            print(f"  {progress.get_stats_str()}")

            # Rate limiting (respect TMDB limits)
            time.sleep(rate_limit)

        elapsed = time.time() - start_time

        # Final summary
        stats = {
            'Total Movies': len(all_movies),
            'Successfully Processed': progress.success,
            'Skipped (Already Done)': progress.skipped,
            'Failed': progress.failed,
            'Total Time': f"{elapsed:.1f}s ({elapsed/60:.1f}min)",
            'Average Speed': f"{elapsed/len(all_movies):.2f}s per movie",
            'Processing Rate': f"{len(all_movies)/elapsed:.2f} movies/sec"
        }

        print_summary(stats)

        return {
            'total': len(all_movies),
            'success': progress.success,
            'skipped': progress.skipped,
            'failed': progress.failed,
            'elapsed': elapsed
        }

    def restore_movie(self, movie_title: str) -> bool:
        """
        Restore original poster for a movie

        Args:
            movie_title: Movie title

        Returns:
            True if restored
        """
        # Find movie in library
        try:
            movie = self.library.get(movie_title)
        except Exception as e:
            logger.error(f"Movie not found: {movie_title}")
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would restore original poster for '{movie_title}'")
            return True

        return self.backup_manager.restore_original(
            library_name=self.library_name,
            item_title=movie_title,
            plex_item=movie,
            year=movie.year
        )

    def restore_library(self) -> int:
        """
        Restore all original posters in library

        Returns:
            Number of posters restored
        """
        backups = self.backup_manager.list_backups(library_name=self.library_name)
        restored_count = 0

        logger.info(f"Restoring {len(backups)} original posters...")

        for backup in backups:
            if self.restore_movie(backup['title']):
                restored_count += 1

        logger.info(f"✓ Restored {restored_count}/{len(backups)} posters")
        return restored_count

    def list_backups(self) -> List[Dict]:
        """List all backed up posters"""
        return self.backup_manager.list_backups(library_name=self.library_name)


def main():
    """Example usage"""
    import json
    import argparse
    from ..utils.logger import setup_logger

    # Parse arguments
    parser = argparse.ArgumentParser(description='Kometizarr Plex Poster Manager')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--dry-run', action='store_true', help='Preview without applying')
    parser.add_argument('--limit', type=int, help='Limit number of movies to process')
    parser.add_argument('--force', action='store_true', help='Force reprocess all movies')
    parser.add_argument('--restore', action='store_true', help='Restore original posters')
    parser.add_argument('--restore-movie', type=str, help='Restore specific movie')
    args = parser.parse_args()

    # Load config
    with open(args.config) as f:
        config = json.load(f)

    # Setup better logging
    setup_logger('kometizarr', level=logging.INFO)

    # Initialize manager
    manager = PlexPosterManager(
        plex_url=config['plex']['url'],
        plex_token=config['plex']['token'],
        library_name=config['plex']['library'],
        tmdb_api_key=config['apis']['tmdb']['api_key'],
        omdb_api_key=config['apis'].get('omdb', {}).get('api_key'),
        mdblist_api_key=config['apis'].get('mdblist', {}).get('api_key'),
        backup_dir=config['output']['directory'],
        badge_style=config['rating_overlay']['badge'].get('style', 'default'),
        dry_run=args.dry_run,
        rating_sources=config['rating_overlay'].get('sources', None)
    )

    # Restore mode
    if args.restore:
        manager.restore_library()
        return

    if args.restore_movie:
        manager.restore_movie(args.restore_movie)
        return

    # Process library
    if config['rating_overlay']['enabled']:
        position = config['rating_overlay']['badge'].get('position', 'northeast')

        manager.process_library(
            limit=args.limit,
            position=position,
            force=args.force
        )


if __name__ == '__main__':
    main()
