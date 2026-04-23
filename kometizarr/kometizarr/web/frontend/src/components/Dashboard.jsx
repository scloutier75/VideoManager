import { useState, useEffect, useRef } from 'react'

function Dashboard({ onStartProcessing, onLibrarySelect }) {
  const [libraries, setLibraries] = useState([])
  const [selectedLibrary, setSelectedLibrary] = useState(null)   // for preview / restore
  const [selectedLibraries, setSelectedLibraries] = useState([]) // for processing (names)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [position, setPosition] = useState('northwest')  // Keep for backward compat display
  const [badgePositions, setBadgePositions] = useState(() => {
    // Load from localStorage or set smart defaults (4 corners)
    // Always merge with defaults so new badge types added in updates are present
    const defaults = {
      tmdb: { x: 2, y: 2 },           // Top-left
      imdb: { x: 70, y: 2 },          // Top-right (70% across to fit ~12% badge + margin)
      rt_critic: { x: 2, y: 78 },      // Bottom-left (78% down to fit ~20% badge + margin)
      rt_audience: { x: 70, y: 78 },   // Bottom-right
      vmgr_score: { x: 2, y: 40 },     // Mid-left (VideoManager quality score)
      resolution_4k: { x: 70, y: 40 }  // Mid-right (4K chip)
    }
    const saved = localStorage.getItem('kometizarr_badge_positions')
    return saved ? { ...defaults, ...JSON.parse(saved) } : defaults
  })
  const [activeDragBadge, setActiveDragBadge] = useState(null)  // Which badge is being dragged
  const [alignmentGuides, setAlignmentGuides] = useState([])  // Visual alignment guides
  const [force, setForce] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewResults, setPreviewResults] = useState(null)  // null = closed, [] = loading/empty
  const [ratingSources, setRatingSources] = useState(() => {
    // Load from localStorage or default to all enabled
    // Merge with defaults so new sources added in updates are always present
    const defaults = {
      tmdb: true,
      imdb: true,
      rt_critic: true,
      rt_audience: true,
      vmgr_score: false,    // VideoManager quality score (requires VIDEOMANAGER_DB_URL)
      resolution_4k: false  // 4K resolution chip
    }
    const saved = localStorage.getItem('kometizarr_rating_sources')
    return saved ? { ...defaults, ...JSON.parse(saved) } : defaults
  })
  const [badgeStyle, setBadgeStyle] = useState(() => {
    // Load from localStorage, deep-merging with defaults so new keys added
    // in upgrades (text_vertical_align, source_colors) are always present.
    const defaults = {
      individual_badge_size: 12,
      font_size_multiplier: 1.0,
      logo_size_multiplier: 1.0,
      rating_color: '#FFD700',    // Global fallback color for all sources
      background_opacity: 128,
      font_family: 'DejaVu Sans Bold',
      text_vertical_align: 50,    // 0 = top of label area (close to logo), 100 = bottom
      source_colors: {            // Per-source label color; null = use global rating_color
        tmdb: null,
        imdb: null,
        rt_critic: null,
        rt_audience: null,
        vmgr_score: '#00C8DC',    // Cyan default for VM score
        resolution_4k: '#FFFFFF', // White default for 4K chip
      },
      source_text_va: {},         // Per-source label vertical position override (0-100)
      source_logo_x_offset: {},   // Per-source logo horizontal offset (% of badge width, -50..+50)
      source_logo_size: {},        // Per-source logo size multiplier override
    }
    const saved = localStorage.getItem('kometizarr_badge_style')
    if (!saved) return defaults
    const p = JSON.parse(saved)
    return {
      ...defaults, ...p,
      source_colors:      { ...defaults.source_colors,      ...(p.source_colors || {}) },
      source_text_va:     { ...defaults.source_text_va,     ...(p.source_text_va || {}) },
      source_logo_x_offset: { ...defaults.source_logo_x_offset, ...(p.source_logo_x_offset || {}) },
      source_logo_size:     { ...defaults.source_logo_size,     ...(p.source_logo_size || {}) },
    }
  })

  // Keep a ref so handleMouseUp can read latest badgePositions without stale closure
  const badgePositionsRef = useRef(badgePositions)
  useEffect(() => { badgePositionsRef.current = badgePositions }, [badgePositions])

  // Persist badge settings to server so webhook/cron use the same settings as the UI
  const persistBadgeSettings = async (patch) => {
    try {
      const res = await fetch('/api/settings')
      const current = await res.json()
      await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...current, ...patch }),
      })
    } catch (e) {
      console.warn('Failed to persist badge settings to server:', e)
    }
  }

  useEffect(() => {
    fetchLibraries()
    // Sync badge settings between server and localStorage on mount.
    // Server is source of truth (webhook/cron read from it).
    // If server has settings, load them into component state.
    // If server is missing settings, push localStorage defaults.
    fetch('/api/settings')
      .then(r => r.json())
      .then(s => {
        if (s.badge_positions) {
          // Merge server value with current state so new keys (added in upgrades) are preserved
          setBadgePositions(prev => {
            const merged = { ...prev, ...s.badge_positions }
            localStorage.setItem('kometizarr_badge_positions', JSON.stringify(merged))
            return merged
          })
        }
        if (s.badge_style) {
          // Deep-merge source_colors so per-source color defaults aren't lost
          setBadgeStyle(prev => {
            const merged = {
              ...prev,
              ...s.badge_style,
              source_colors:        { ...(prev.source_colors || {}),        ...(s.badge_style.source_colors || {}) },
              source_text_va:       { ...(prev.source_text_va || {}),       ...(s.badge_style.source_text_va || {}) },
              source_logo_x_offset: { ...(prev.source_logo_x_offset || {}), ...(s.badge_style.source_logo_x_offset || {}) },
              source_logo_size:     { ...(prev.source_logo_size || {}),      ...(s.badge_style.source_logo_size || {}) },
            }
            localStorage.setItem('kometizarr_badge_style', JSON.stringify(merged))
            return merged
          })
        }
        if (s.rating_sources) {
          // Merge server value with current state so new keys (added in upgrades) are preserved
          setRatingSources(prev => {
            const merged = { ...prev, ...s.rating_sources }
            localStorage.setItem('kometizarr_rating_sources', JSON.stringify(merged))
            return merged
          })
        }
        // Push localStorage defaults for anything the server doesn't have yet
        if (!s.badge_positions || !s.badge_style || !s.rating_sources) {
          persistBadgeSettings({
            badge_positions: s.badge_positions || badgePositions,
            badge_style: s.badge_style || badgeStyle,
            rating_sources: s.rating_sources || ratingSources,
          })
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (selectedLibraries.length > 0) {
      fetchAggregatedStats(selectedLibraries)
    } else {
      setStats(null)
    }
  }, [selectedLibraries])

  const fetchLibraries = async () => {
    try {
      const res = await fetch('/api/libraries')
      const data = await res.json()
      if (data.libraries) {
        setLibraries(data.libraries)
        if (data.libraries.length > 0) {
          setSelectedLibrary(data.libraries[0])
          setSelectedLibraries(data.libraries.map(l => l.name)) // select all by default
        }
      }
    } catch (error) {
      console.error('Failed to fetch libraries:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchAggregatedStats = async (libraryNames) => {
    try {
      const results = await Promise.all(
        libraryNames.map(name =>
          fetch(`/api/library/${name}/stats`).then(r => r.json())
        )
      )
      const aggregated = results.reduce(
        (acc, data) => ({
          total_items: acc.total_items + (data.total_items || 0),
          processed_items: acc.processed_items + (data.processed_items || 0),
        }),
        { total_items: 0, processed_items: 0 }
      )
      aggregated.success_rate = aggregated.total_items > 0
        ? ((aggregated.processed_items / aggregated.total_items) * 100).toFixed(1)
        : '0.0'
      setStats(aggregated)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }

  const toggleLibrarySelection = (lib) => {
    const isDeselecting = selectedLibraries.includes(lib.name)
    const newSelected = isDeselecting
      ? selectedLibraries.filter(n => n !== lib.name)
      : [...selectedLibraries, lib.name]
    setSelectedLibraries(newSelected)
    // Update selectedLibrary for preview/restore: use clicked lib if selecting,
    // otherwise fall back to first remaining selected library
    if (!isDeselecting) {
      setSelectedLibrary(lib)
    } else if (newSelected.length > 0) {
      setSelectedLibrary(libraries.find(l => l.name === newSelected[0]))
    } else {
      setSelectedLibrary(null)
    }
    if (onLibrarySelect) onLibrarySelect(lib)
  }

  const toggleRatingSource = (source) => {
    const updated = { ...ratingSources, [source]: !ratingSources[source] }
    setRatingSources(updated)
    localStorage.setItem('kometizarr_rating_sources', JSON.stringify(updated))
    persistBadgeSettings({ rating_sources: updated })
  }

  const updateBadgeStyle = (key, value) => {
    const updated = { ...badgeStyle, [key]: value }
    setBadgeStyle(updated)
    localStorage.setItem('kometizarr_badge_style', JSON.stringify(updated))
    persistBadgeSettings({ badge_style: updated })
  }

  const handlePosterDrag = (e, badgeSource) => {
    if (!activeDragBadge && !badgeSource) return  // Not dragging

    const source = badgeSource || activeDragBadge
    if (!source || !ratingSources[source]) return  // Badge not enabled

    const rect = e.currentTarget.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const clickY = e.clientY - rect.top

    // Calculate position as percentage of poster dimensions (0-100)
    // Individual badges are small (~12% of poster width)
    const badgeWidthPercent = badgeStyle.individual_badge_size || 12
    const badgeHeightPercent = badgeWidthPercent * 1.4  // 1.4x aspect ratio

    // Center badge on cursor
    let xPercent = (clickX / rect.width) * 100 - (badgeWidthPercent / 2)
    let yPercent = (clickY / rect.height) * 100 - (badgeHeightPercent / 2)

    // Detect alignment with other badges (before clamping)
    const guides = []
    const threshold = 2  // Snap within 2%
    let alignedX = false
    let alignedY = false

    Object.keys(badgePositions).forEach(otherSource => {
      if (otherSource === source || !ratingSources[otherSource]) return

      const other = badgePositions[otherSource]
      const otherRight = other.x + badgeWidthPercent
      const otherBottom = other.y + badgeHeightPercent
      const otherCenterX = other.x + badgeWidthPercent / 2
      const otherCenterY = other.y + badgeHeightPercent / 2

      const dragRight = xPercent + badgeWidthPercent
      const dragBottom = yPercent + badgeHeightPercent
      const dragCenterX = xPercent + badgeWidthPercent / 2
      const dragCenterY = yPercent + badgeHeightPercent / 2

      // Check vertical alignments (X-axis) - only snap if not already aligned
      if (!alignedX) {
        if (Math.abs(xPercent - other.x) < threshold) {
          // Left edges align
          xPercent = other.x
          guides.push({ type: 'vertical', position: other.x })
          alignedX = true
        } else if (Math.abs(dragRight - otherRight) < threshold) {
          // Right edges align
          xPercent = otherRight - badgeWidthPercent
          guides.push({ type: 'vertical', position: otherRight })
          alignedX = true
        } else if (Math.abs(dragCenterX - otherCenterX) < threshold) {
          // Centers align
          xPercent = otherCenterX - badgeWidthPercent / 2
          guides.push({ type: 'vertical', position: otherCenterX })
          alignedX = true
        }
      }

      // Check horizontal alignments (Y-axis) - only snap if not already aligned
      if (!alignedY) {
        if (Math.abs(yPercent - other.y) < threshold) {
          // Top edges align
          yPercent = other.y
          guides.push({ type: 'horizontal', position: other.y })
          alignedY = true
        } else if (Math.abs(dragBottom - otherBottom) < threshold) {
          // Bottom edges align
          yPercent = otherBottom - badgeHeightPercent
          guides.push({ type: 'horizontal', position: otherBottom })
          alignedY = true
        } else if (Math.abs(dragCenterY - otherCenterY) < threshold) {
          // Centers align
          yPercent = otherCenterY - badgeHeightPercent / 2
          guides.push({ type: 'horizontal', position: otherCenterY })
          alignedY = true
        }
      }
    })

    // Clamp to edges AFTER alignment - simple 0-100% bounds (badges can overlap edges)
    xPercent = Math.max(0, Math.min(xPercent, 100))
    yPercent = Math.max(0, Math.min(yPercent, 100))

    setAlignmentGuides(guides)

    const newPosition = { x: Math.round(xPercent), y: Math.round(yPercent) }

    // Update only this badge's position
    const updated = { ...badgePositions, [source]: newPosition }
    setBadgePositions(updated)
    localStorage.setItem('kometizarr_badge_positions', JSON.stringify(updated))
  }

  const handleBadgeMouseDown = (e, badgeSource) => {
    e.stopPropagation()  // Prevent poster click
    setActiveDragBadge(badgeSource)
    // Don't move on initial click - only move when dragging (mousemove)
  }

  const handlePosterMouseMove = (e) => {
    if (activeDragBadge) {
      handlePosterDrag(e)
    }
  }

  const handleMouseUp = () => {
    if (activeDragBadge) {
      // Save final drag position to server (use ref to get latest state)
      persistBadgeSettings({ badge_positions: badgePositionsRef.current })
    }
    setActiveDragBadge(null)
    setAlignmentGuides([])  // Clear alignment guides
  }

  const startProcessing = async () => {
    if (selectedLibraries.length === 0) return

    const enabledBadgePositions = {}
    Object.keys(ratingSources).forEach(source => {
      if (ratingSources[source] && badgePositions[source]) {
        enabledBadgePositions[source] = badgePositions[source]
      }
    })

    const commonOptions = {
      position,
      badge_positions: enabledBadgePositions,
      force,
      rating_sources: ratingSources,
      badge_style: badgeStyle,
    }

    try {
      const isBatch = selectedLibraries.length > 1
      const res = await fetch(isBatch ? '/api/process-batch' : '/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          isBatch
            ? { library_names: selectedLibraries, ...commonOptions }
            : { library_name: selectedLibraries[0], ...commonOptions }
        ),
      })

      const data = await res.json()
      if (data.status === 'started') {
        onStartProcessing()
      }
    } catch (error) {
      console.error('Failed to start processing:', error)
    }
  }

  const restoreOriginals = async () => {
    if (!selectedLibrary) return

    if (!confirm(`Restore all original posters in ${selectedLibrary.name}? This will remove all overlays.`)) {
      return
    }

    try {
      const res = await fetch('/api/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          library_name: selectedLibrary.name,
        }),
      })

      const data = await res.json()
      if (data.status === 'started') {
        onStartProcessing() // Use same callback to show progress view
      } else if (data.error) {
        alert(`Error: ${data.error}`)
      }
    } catch (error) {
      console.error('Failed to restore originals:', error)
      alert('Failed to restore originals')
    }
  }

  const previewPosters = async () => {
    if (!selectedLibrary) return
    setPreviewLoading(true)
    setPreviewResults([])

    const enabledBadgePositions = {}
    Object.keys(ratingSources).forEach(source => {
      if (ratingSources[source] && badgePositions[source]) {
        enabledBadgePositions[source] = badgePositions[source]
      }
    })

    try {
      const res = await fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          library_name: selectedLibrary.name,
          badge_positions: enabledBadgePositions,
          rating_sources: ratingSources,
          badge_style: badgeStyle,
          count: 3,
        }),
      })
      const data = await res.json()
      setPreviewResults(data.previews || [])
    } catch (error) {
      console.error('Preview failed:', error)
      setPreviewResults([])
    } finally {
      setPreviewLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading libraries...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Library Selection */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Select Libraries</h2>
          {libraries.length > 1 && (
            <button
              onClick={() => {
                const allSelected = selectedLibraries.length === libraries.length
                setSelectedLibraries(allSelected ? [] : libraries.map(l => l.name))
                setSelectedLibrary(allSelected ? null : libraries[0])
              }}
              className="text-xs text-gray-400 hover:text-gray-200 transition"
            >
              {selectedLibraries.length === libraries.length ? 'Deselect all' : 'Select all'}
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {libraries.map((lib) => {
            const isSelected = selectedLibraries.includes(lib.name)
            return (
              <button
                key={lib.name}
                onClick={() => toggleLibrarySelection(lib)}
                className={`p-4 rounded-lg border-2 transition relative text-left ${
                  isSelected
                    ? 'border-blue-500 bg-blue-900/20'
                    : 'border-gray-700 hover:border-gray-600'
                }`}
              >
                {/* Checkbox indicator */}
                <div className={`absolute top-3 right-3 w-5 h-5 rounded border-2 flex items-center justify-center text-xs font-bold transition ${
                  isSelected ? 'border-blue-500 bg-blue-500 text-white' : 'border-gray-500'
                }`}>
                  {isSelected && '✓'}
                </div>
                <div className="font-semibold pr-7">{lib.name}</div>
                <div className="text-sm text-gray-400 mt-1">
                  {lib.type === 'movie' ? '🎬' : '📺'} {lib.count} items
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Library Stats */}
      {stats && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-semibold mb-4">Library Statistics</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-gray-400 text-sm">Total Items</div>
              <div className="text-3xl font-bold mt-1">{stats.total_items}</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-gray-400 text-sm">With Backups</div>
              <div className="text-3xl font-bold mt-1 text-green-400">
                {stats.processed_items}
              </div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-gray-400 text-sm">Backup Coverage</div>
              <div className="text-3xl font-bold mt-1 text-blue-400">
                {stats.success_rate}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Processing Options */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4">Processing Options</h2>
        <div className="space-y-4">
          {/* Position & Styling - Side by Side Layout */}
          <div>
            <label className="block text-sm font-medium mb-2">Badge Positions & Styling</label>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="flex items-start gap-6">
                {/* LEFT: Draggable Poster Preview */}
                <div className="flex-shrink-0">
                  <svg
                    viewBox="0 0 120 168"
                    className="w-48 h-auto select-none"
                    onMouseMove={handlePosterMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                  >
                    {/* Poster Background */}
                    <rect x="0" y="0" width="120" height="168" fill="#1f2937" stroke="#4b5563" strokeWidth="2" rx="3" />

                    {/* Individual Badges - dynamically sized and styled */}
                    {(() => {
                      // Calculate badge dimensions based on style settings
                      const badgeSizePercent = badgeStyle.individual_badge_size || 12
                      const badgeWidth = (badgeSizePercent / 100) * 120  // Scale to SVG viewBox
                      const badgeHeight = badgeWidth * 1.4  // 1.4 aspect ratio
                      const logoMultiplier = badgeStyle.logo_size_multiplier || 1.0
                      const fontMultiplier = badgeStyle.font_size_multiplier || 1.0
                      // Logo occupies top 60% of badge, scaled by logo_size_multiplier (max 2.0 → full area)
                      const logoAreaHeight = badgeHeight * 0.6 * Math.min(logoMultiplier / 2.0, 1.0)
                      // Font size applies to bottom 40% (rating number), scaled by font_size_multiplier
                      const fontSize = (badgeWidth / 14) * 8 * fontMultiplier
                      const opacity = (badgeStyle.background_opacity || 128) / 255
                      // Text vertical position mirrors backend extended range:
                      // slider [0,100] → effective_va = -0.60 + slider/100 * 1.60
                      // Then text Y = badge_height * (0.6 + 0.4 * effective_va)
                      const textVA = (badgeStyle.text_vertical_align ?? 50) / 100
                      const effectiveVA = -0.60 + textVA * 1.60
                      const textYFrac = 0.6 + 0.4 * effectiveVA  // fraction of badgeHeight — global fallback

                      // Per-source label VA: reads source_text_va override, falls back to global
                      const getTextYFrac = (src) => {
                        const va = (badgeStyle.source_text_va || {})[src]
                        if (va == null) return textYFrac
                        const eff = -0.60 + (va / 100) * 1.60
                        return 0.6 + 0.4 * eff
                      }

                      // Per-source logo X shift in SVG units (badgeWidth * offset%)
                      const getLogoXShift = (src) => {
                        const off = (badgeStyle.source_logo_x_offset || {})[src] ?? 0
                        return badgeWidth * (off / 100)
                      }

                      // Per-source logo scale: source_logo_size[src] ?? global logo_size_multiplier
                      const getLogoScale = (src) => {
                        return (badgeStyle.source_logo_size || {})[src] ?? (badgeStyle.logo_size_multiplier || 1.0)
                      }
                      // Per-source logo rect height (mirrors backend formula)
                      const getLogoPxHeight = (src) => badgeHeight * 0.6 * Math.min(getLogoScale(src) / 2.0, 1.0) * 0.85

                      // Per-source color: source_colors[source] || global rating_color
                      const getSourceColor = (src) => {
                        const sc = badgeStyle.source_colors || {}
                        return sc[src] || badgeStyle.rating_color || '#FFD700'
                      }

                      // Map font family to CSS font-family for SVG
                      const getFontFamily = (fontName) => {
                        if (fontName.includes('Mono')) return 'monospace'
                        if (fontName.includes('Serif')) return 'serif'
                        return 'sans-serif'
                      }

                      const getFontStyle = (fontName) => {
                        return fontName.includes('Oblique') || fontName.includes('Italic') ? 'italic' : 'normal'
                      }

                      const getFontWeight = (fontName) => {
                        return fontName.includes('Bold') ? 'bold' : 'normal'
                      }

                      const fontFamily = getFontFamily(badgeStyle.font_family || 'DejaVu Sans Bold')
                      const fontStyle = getFontStyle(badgeStyle.font_family || 'DejaVu Sans Bold')
                      const fontWeight = getFontWeight(badgeStyle.font_family || 'DejaVu Sans Bold')

                      return (
                        <>
                          {ratingSources.tmdb && badgePositions.tmdb && (
                            <g
                              className="cursor-move"
                              onMouseDown={(e) => handleBadgeMouseDown(e, 'tmdb')}
                            >
                              <rect x={(badgePositions.tmdb.x / 100) * 120} y={(badgePositions.tmdb.y / 100) * 168} width={badgeWidth} height={badgeHeight} fill="#000" fillOpacity={opacity} rx="2" />
                              <rect x={(badgePositions.tmdb.x / 100) * 120 + badgeWidth * 0.1 + getLogoXShift('tmdb')} y={(badgePositions.tmdb.y / 100) * 168 + badgeHeight * 0.05} width={badgeWidth * 0.8} height={getLogoPxHeight('tmdb')} fill="#4a9eff" fillOpacity={0.35} rx="1" className="pointer-events-none" />
                              <text x={(badgePositions.tmdb.x / 100) * 120 + badgeWidth / 2} y={(badgePositions.tmdb.y / 100) * 168 + badgeHeight * getTextYFrac('tmdb')} fontSize={fontSize} fill={getSourceColor('tmdb')} textAnchor="middle" dominantBaseline="middle" fontFamily={fontFamily} fontStyle={fontStyle} fontWeight={fontWeight} className="pointer-events-none select-none">T</text>
                            </g>
                          )}

                          {ratingSources.imdb && badgePositions.imdb && (
                            <g
                              className="cursor-move"
                              onMouseDown={(e) => handleBadgeMouseDown(e, 'imdb')}
                            >
                              <rect x={(badgePositions.imdb.x / 100) * 120} y={(badgePositions.imdb.y / 100) * 168} width={badgeWidth} height={badgeHeight} fill="#000" fillOpacity={opacity} rx="2" />
                              <rect x={(badgePositions.imdb.x / 100) * 120 + badgeWidth * 0.1 + getLogoXShift('imdb')} y={(badgePositions.imdb.y / 100) * 168 + badgeHeight * 0.05} width={badgeWidth * 0.8} height={getLogoPxHeight('imdb')} fill="#f5c518" fillOpacity={0.35} rx="1" className="pointer-events-none" />
                              <text x={(badgePositions.imdb.x / 100) * 120 + badgeWidth / 2} y={(badgePositions.imdb.y / 100) * 168 + badgeHeight * getTextYFrac('imdb')} fontSize={fontSize} fill={getSourceColor('imdb')} textAnchor="middle" dominantBaseline="middle" fontFamily={fontFamily} fontStyle={fontStyle} fontWeight={fontWeight} className="pointer-events-none select-none">I</text>
                            </g>
                          )}

                          {ratingSources.rt_critic && badgePositions.rt_critic && (
                            <g
                              className="cursor-move"
                              onMouseDown={(e) => handleBadgeMouseDown(e, 'rt_critic')}
                            >
                              <rect x={(badgePositions.rt_critic.x / 100) * 120} y={(badgePositions.rt_critic.y / 100) * 168} width={badgeWidth} height={badgeHeight} fill="#000" fillOpacity={opacity} rx="2" />
                              <rect x={(badgePositions.rt_critic.x / 100) * 120 + badgeWidth * 0.1 + getLogoXShift('rt_critic')} y={(badgePositions.rt_critic.y / 100) * 168 + badgeHeight * 0.05} width={badgeWidth * 0.8} height={getLogoPxHeight('rt_critic')} fill="#fa320a" fillOpacity={0.35} rx="1" className="pointer-events-none" />
                              <text x={(badgePositions.rt_critic.x / 100) * 120 + badgeWidth / 2} y={(badgePositions.rt_critic.y / 100) * 168 + badgeHeight * getTextYFrac('rt_critic')} fontSize={fontSize} fill={getSourceColor('rt_critic')} textAnchor="middle" dominantBaseline="middle" fontFamily={fontFamily} fontStyle={fontStyle} fontWeight={fontWeight} className="pointer-events-none select-none">C</text>
                            </g>
                          )}

                          {ratingSources.rt_audience && badgePositions.rt_audience && (
                            <g
                              className="cursor-move"
                              onMouseDown={(e) => handleBadgeMouseDown(e, 'rt_audience')}
                            >
                              <rect x={(badgePositions.rt_audience.x / 100) * 120} y={(badgePositions.rt_audience.y / 100) * 168} width={badgeWidth} height={badgeHeight} fill="#000" fillOpacity={opacity} rx="2" />
                              <rect x={(badgePositions.rt_audience.x / 100) * 120 + badgeWidth * 0.1 + getLogoXShift('rt_audience')} y={(badgePositions.rt_audience.y / 100) * 168 + badgeHeight * 0.05} width={badgeWidth * 0.8} height={getLogoPxHeight('rt_audience')} fill="#fa320a" fillOpacity={0.25} rx="1" className="pointer-events-none" />
                              <text x={(badgePositions.rt_audience.x / 100) * 120 + badgeWidth / 2} y={(badgePositions.rt_audience.y / 100) * 168 + badgeHeight * getTextYFrac('rt_audience')} fontSize={fontSize} fill={getSourceColor('rt_audience')} textAnchor="middle" dominantBaseline="middle" fontFamily={fontFamily} fontStyle={fontStyle} fontWeight={fontWeight} className="pointer-events-none select-none">A</text>
                            </g>
                          )}

                          {/* VideoManager quality score badge */}
                          {ratingSources.vmgr_score && badgePositions.vmgr_score && (
                            <g
                              className="cursor-move"
                              onMouseDown={(e) => handleBadgeMouseDown(e, 'vmgr_score')}
                            >
                              <rect x={(badgePositions.vmgr_score.x / 100) * 120} y={(badgePositions.vmgr_score.y / 100) * 168} width={badgeWidth} height={badgeHeight} fill="#000" fillOpacity={opacity} rx="2" />
                              {/* VM logo image */}
                              <image
                                href="/assets/logos/vmgr.png"
                                x={(badgePositions.vmgr_score.x / 100) * 120 + badgeWidth * 0.1 + getLogoXShift('vmgr_score')}
                                y={(badgePositions.vmgr_score.y / 100) * 168 + badgeHeight * 0.05}
                                width={badgeWidth * 0.8}
                                height={badgeHeight * 0.50 * getLogoScale('vmgr_score')}
                                preserveAspectRatio="xMidYMid meet"
                                className="pointer-events-none"
                              />
                              <text x={(badgePositions.vmgr_score.x / 100) * 120 + badgeWidth / 2} y={(badgePositions.vmgr_score.y / 100) * 168 + badgeHeight * getTextYFrac('vmgr_score')} fontSize={fontSize} fill={getSourceColor('vmgr_score')} textAnchor="middle" dominantBaseline="middle" fontFamily={fontFamily} fontStyle={fontStyle} fontWeight={fontWeight} className="pointer-events-none select-none">8.4</text>
                            </g>
                          )}

                          {/* 4K resolution chip */}
                          {ratingSources.resolution_4k && badgePositions.resolution_4k && (
                            <g
                              className="cursor-move"
                              onMouseDown={(e) => handleBadgeMouseDown(e, 'resolution_4k')}
                            >
                              <rect x={(badgePositions.resolution_4k.x / 100) * 120} y={(badgePositions.resolution_4k.y / 100) * 168} width={badgeWidth} height={badgeWidth * 0.65} fill="#0064dc" fillOpacity={0.80} rx="2" />
                              <text x={(badgePositions.resolution_4k.x / 100) * 120 + badgeWidth / 2} y={(badgePositions.resolution_4k.y / 100) * 168 + badgeWidth * 0.325} fontSize={fontSize * 1.1} fill={getSourceColor('resolution_4k')} textAnchor="middle" dominantBaseline="middle" fontFamily={fontFamily} fontWeight="bold" className="pointer-events-none select-none">4K</text>
                            </g>
                          )}
                        </>
                      )
                    })()}

                    {/* Alignment Guides */}
                    {alignmentGuides.map((guide, index) => {
                      if (guide.type === 'vertical') {
                        // Vertical line (for X-axis alignment)
                        const x = (guide.position / 100) * 120
                        return (
                          <line
                            key={`guide-${index}`}
                            x1={x}
                            y1={0}
                            x2={x}
                            y2={168}
                            stroke="#3b82f6"
                            strokeWidth="1"
                            strokeDasharray="4,4"
                            className="pointer-events-none"
                          />
                        )
                      } else {
                        // Horizontal line (for Y-axis alignment)
                        const y = (guide.position / 100) * 168
                        return (
                          <line
                            key={`guide-${index}`}
                            x1={0}
                            y1={y}
                            x2={120}
                            y2={y}
                            stroke="#3b82f6"
                            strokeWidth="1"
                            strokeDasharray="4,4"
                            className="pointer-events-none"
                          />
                        )
                      }
                    })}
                  </svg>
                  <div className="text-xs text-gray-500 mt-2 space-y-1">
                    <p className="font-medium">💡 Drag badges to position</p>
                    <div className="text-gray-400 leading-relaxed">
                      <span className="font-bold text-white">T</span>=<span className="font-bold">TMDB</span> • <span className="font-bold text-white">I</span>=<span className="font-bold">IMDb</span> • <span className="font-bold text-white">C</span>=<span className="font-bold">RT Critic</span> • <span className="font-bold text-white">A</span>=<span className="font-bold">RT Audience</span>
                    </div>
                  </div>
                </div>

                {/* RIGHT: Styling Controls */}
                <div className="flex-1 space-y-3">
                  {/* Badge Size */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Badge Size: {Math.round(((badgeStyle.individual_badge_size - 8) / (30 - 8)) * 100)}%
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      value={Math.round(((badgeStyle.individual_badge_size - 8) / (30 - 8)) * 100)}
                      onChange={(e) => {
                        // Map 0-100 slider to 8-30% actual badge size
                        const sliderValue = parseInt(e.target.value)
                        const actualSize = 8 + (sliderValue / 100) * (30 - 8)
                        updateBadgeStyle('individual_badge_size', Math.round(actualSize))
                      }}
                      className="w-full accent-blue-500"
                    />
                  </div>

                  {/* Font Size */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Font Size: {badgeStyle.font_size_multiplier.toFixed(1)}x
                    </label>
                    <input
                      type="range"
                      min="0.5"
                      max="2.0"
                      step="0.1"
                      value={badgeStyle.font_size_multiplier}
                      onChange={(e) => updateBadgeStyle('font_size_multiplier', parseFloat(e.target.value))}
                      className="w-full accent-blue-500"
                    />
                  </div>

                  {/* Logo Size */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Logo Size: {(badgeStyle.logo_size_multiplier || 1.0).toFixed(1)}x
                    </label>
                    <input
                      type="range"
                      min="0.3"
                      max="2.0"
                      step="0.1"
                      value={badgeStyle.logo_size_multiplier || 1.0}
                      onChange={(e) => updateBadgeStyle('logo_size_multiplier', parseFloat(e.target.value))}
                      className="w-full accent-blue-500"
                    />
                  </div>

                  {/* Label Position */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Label Position: {badgeStyle.text_vertical_align ?? 50}%
                      {(badgeStyle.text_vertical_align ?? 50) <= 25 ? ' (over logo)'
                        : (badgeStyle.text_vertical_align ?? 50) <= 45 ? ' (close to logo)'
                        : (badgeStyle.text_vertical_align ?? 50) <= 60 ? ' (centered)'
                        : ' (bottom)'}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      value={badgeStyle.text_vertical_align ?? 50}
                      onChange={(e) => updateBadgeStyle('text_vertical_align', parseInt(e.target.value))}
                      className="w-full accent-blue-500"
                    />
                  </div>

                  {/* Per-source fine-tuning: label VA + logo X offset */}
                  {(() => {
                    const SOURCES = [
                      { key: 'tmdb',          label: 'TMDB' },
                      { key: 'imdb',          label: 'IMDb' },
                      { key: 'rt_critic',     label: 'RT Critic' },
                      { key: 'rt_audience',   label: 'RT Audience' },
                      { key: 'vmgr_score',    label: 'VM Score' },
                      { key: 'resolution_4k', label: '4K Chip' },
                    ]
                    // Only show for sources that are currently enabled
                    const activeSources = SOURCES.filter(s => ratingSources[s.key])
                    if (activeSources.length === 0) return null
                    return (
                      <div>
                        <label className="text-xs text-gray-400 block mb-2">Per-source fine-tuning</label>
                        <div className="space-y-3">
                          {activeSources.map(({ key, label }) => {
                            const va = (badgeStyle.source_text_va || {})[key] ?? null
                            const xoff = (badgeStyle.source_logo_x_offset || {})[key] ?? null
                            const ssize = (badgeStyle.source_logo_size || {})[key] ?? null
                            return (
                              <div key={key} className="bg-gray-800/60 rounded p-2 space-y-1">
                                <div className="text-xs font-medium text-gray-300">{label}</div>
                                {/* Label vertical position */}
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-gray-500 w-20 shrink-0">Label VA</span>
                                  <input
                                    type="range" min="0" max="100" step="5"
                                    value={va ?? (badgeStyle.text_vertical_align ?? 50)}
                                    onChange={(e) => {
                                      const newVa = { ...(badgeStyle.source_text_va || {}), [key]: parseInt(e.target.value) }
                                      updateBadgeStyle('source_text_va', newVa)
                                    }}
                                    className="flex-1 accent-purple-500"
                                  />
                                  <span className="text-xs text-gray-500 w-8 text-right">{va ?? (badgeStyle.text_vertical_align ?? 50)}%</span>
                                  {va !== null && (
                                    <button
                                      onClick={() => {
                                        const newVa = { ...(badgeStyle.source_text_va || {}) }
                                        delete newVa[key]
                                        updateBadgeStyle('source_text_va', newVa)
                                      }}
                                      className="text-xs text-gray-600 hover:text-gray-400 w-4"
                                      title="Reset to global"
                                    >×</button>
                                  )}
                                </div>
                                {/* Logo horizontal offset */}
                                {key !== 'resolution_4k' && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 w-20 shrink-0">Logo X</span>
                                    <input
                                      type="range" min="-50" max="50" step="1"
                                      value={xoff ?? 0}
                                      onChange={(e) => {
                                        const newX = { ...(badgeStyle.source_logo_x_offset || {}), [key]: parseInt(e.target.value) }
                                        updateBadgeStyle('source_logo_x_offset', newX)
                                      }}
                                      className="flex-1 accent-orange-500"
                                    />
                                    <span className="text-xs text-gray-500 w-8 text-right">{xoff ?? 0}%</span>
                                    {xoff !== null && xoff !== 0 && (
                                      <button
                                        onClick={() => {
                                          const newX = { ...(badgeStyle.source_logo_x_offset || {}) }
                                          delete newX[key]
                                          updateBadgeStyle('source_logo_x_offset', newX)
                                        }}
                                        className="text-xs text-gray-600 hover:text-gray-400 w-4"
                                        title="Reset to center"
                                      >×</button>
                                    )}
                                  </div>
                                )}
                                {/* Logo size multiplier */}
                                {key !== 'resolution_4k' && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 w-20 shrink-0">Logo Size</span>
                                    <input
                                      type="range" min="0.3" max="2.0" step="0.05"
                                      value={ssize ?? (badgeStyle.logo_size_multiplier || 1.0)}
                                      onChange={(e) => {
                                        const newSz = { ...(badgeStyle.source_logo_size || {}), [key]: parseFloat(e.target.value) }
                                        updateBadgeStyle('source_logo_size', newSz)
                                      }}
                                      className="flex-1 accent-green-500"
                                    />
                                    <span className="text-xs text-gray-500 w-8 text-right">{(ssize ?? (badgeStyle.logo_size_multiplier || 1.0)).toFixed(2)}×</span>
                                    {ssize !== null && (
                                      <button
                                        onClick={() => {
                                          const newSz = { ...(badgeStyle.source_logo_size || {}) }
                                          delete newSz[key]
                                          updateBadgeStyle('source_logo_size', newSz)
                                        }}
                                        className="text-xs text-gray-600 hover:text-gray-400 w-4"
                                        title="Reset to global"
                                      >×</button>
                                    )}
                                  </div>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })()}

                  {/* Font and Color - Side by Side */}
                  <div className="grid grid-cols-2 gap-3">
                    {/* Font Family */}
                    <div>
                      <label className="text-xs text-gray-400 block mb-1">
                        Font
                      </label>
                      <select
                        value={badgeStyle.font_family}
                        onChange={(e) => updateBadgeStyle('font_family', e.target.value)}
                        className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white"
                      >
                        <option value="DejaVu Sans Bold">Sans Bold (Default)</option>
                        <option value="DejaVu Sans">Sans Regular</option>
                        <option value="DejaVu Sans Bold Oblique">Sans Bold Italic</option>
                        <option value="DejaVu Sans Oblique">Sans Italic</option>
                        <option value="DejaVu Serif Bold">Serif Bold</option>
                        <option value="DejaVu Serif">Serif Regular</option>
                        <option value="DejaVu Serif Bold Italic">Serif Bold Italic</option>
                        <option value="DejaVu Serif Italic">Serif Italic</option>
                        <option value="DejaVu Sans Mono Bold">Mono Bold</option>
                        <option value="DejaVu Sans Mono">Mono Regular</option>
                        <option value="DejaVu Sans Mono Oblique">Mono Italic</option>
                      </select>
                    </div>

                    {/* Rating Color */}
                    <div>
                      <label className="text-xs text-gray-400 block mb-1">
                        Color
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={badgeStyle.rating_color}
                          onChange={(e) => updateBadgeStyle('rating_color', e.target.value)}
                          className="w-10 h-8 rounded border border-gray-700 bg-gray-800 cursor-pointer"
                        />
                        <span className="text-xs text-gray-400 font-mono text-xs">{badgeStyle.rating_color}</span>
                      </div>
                    </div>
                  </div>

                  {/* Background Opacity */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Background: {Math.round((badgeStyle.background_opacity / 255) * 100)}%
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="255"
                      step="5"
                      value={badgeStyle.background_opacity}
                      onChange={(e) => updateBadgeStyle('background_opacity', parseInt(e.target.value))}
                      className="w-full accent-blue-500"
                    />
                  </div>

                  {/* Reset Button */}
                  <button
                    onClick={() => {
                      const defaults = {
                        individual_badge_size: 12,
                        font_size_multiplier: 1.0,
                        logo_size_multiplier: 1.0,
                        rating_color: '#FFD700',
                        background_opacity: 128,
                        font_family: 'DejaVu Sans Bold',
                        text_vertical_align: 50,
                        source_colors: {
                          tmdb: null, imdb: null, rt_critic: null, rt_audience: null,
                          vmgr_score: '#00C8DC', resolution_4k: '#FFFFFF'
                        },
                        source_text_va: {},
                        source_logo_x_offset: {},
                        source_logo_size: {},
                      }
                      setBadgeStyle(defaults)
                      localStorage.setItem('kometizarr_badge_style', JSON.stringify(defaults))
                    }}
                    className="w-full text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded border border-gray-700 transition"
                  >
                    ↺ Reset Styling
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Force */}
          <div className="flex items-center">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="mr-3"
              id="force-checkbox"
            />
            <label htmlFor="force-checkbox" className="text-sm">
              Force reprocess (use when updating ratings or changing which sources to display)
            </label>
          </div>
          {force && (
            <div className="mt-2 p-3 bg-blue-900/20 border border-blue-700/50 rounded text-sm text-blue-300">
              ℹ️ Uses original posters from backup to apply fresh overlays with updated ratings. Original backups are never overwritten.
            </div>
          )}

          {/* Rating Sources */}
          <div>
            <label className="block text-sm font-medium mb-2">Rating Sources to Display</label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { key: 'tmdb',         label: '🎬 TMDB',            defaultColor: null },
                { key: 'imdb',         label: '⭐ IMDb',            defaultColor: null },
                { key: 'rt_critic',    label: '🍅 RT Critic',       defaultColor: null },
                { key: 'rt_audience',  label: '🍿 RT Audience',     defaultColor: null },
                { key: 'vmgr_score',   label: '🎯 VM Quality Score',defaultColor: '#00C8DC' },
                { key: 'resolution_4k',label: '📺 4K Chip',         defaultColor: '#FFFFFF' },
              ].map(({ key, label, defaultColor }) => {
                const srcColor = (badgeStyle.source_colors || {})[key]
                const colorValue = srcColor || badgeStyle.rating_color || defaultColor || '#FFD700'
                return (
                  <div key={key} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={ratingSources[key] || false}
                      onChange={() => toggleRatingSource(key)}
                      className="flex-none"
                      id={`${key}-checkbox`}
                    />
                    <label htmlFor={`${key}-checkbox`} className="text-sm flex-1 min-w-0 truncate cursor-pointer">
                      {label}
                    </label>
                    <input
                      type="color"
                      value={colorValue}
                      onChange={(e) => {
                        const newSC = { ...(badgeStyle.source_colors || {}), [key]: e.target.value }
                        updateBadgeStyle('source_colors', newSC)
                      }}
                      className="flex-none w-6 h-5 rounded border border-gray-600 bg-transparent cursor-pointer"
                      title={`${label} label color`}
                    />
                  </div>
                )
              })}
            </div>
            {!Object.values(ratingSources).some(v => v) && (
              <div className="mt-2 p-3 bg-red-900/20 border border-red-700/50 rounded text-sm text-red-300">
                ⚠️ At least one rating source must be selected
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={restoreOriginals}
              disabled={!selectedLibrary}
              className="bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition"
            >
              🔄 Restore
            </button>
            <button
              onClick={previewPosters}
              disabled={!selectedLibrary || previewLoading}
              className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition"
            >
              {previewLoading ? '⏳ Generating…' : '🔍 Preview'}
            </button>
            <button
              onClick={startProcessing}
              disabled={selectedLibraries.length === 0}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition"
            >
              {selectedLibraries.length > 1 ? `▶️ Process (${selectedLibraries.length})` : '▶️ Process'}
            </button>
          </div>
        </div>
      </div>
      <PreviewModal
        results={previewResults}
        loading={previewLoading}
        onClose={() => setPreviewResults(null)}
      />
    </div>
  )
}

// Preview Modal — rendered outside the main panel so it overlays everything
function PreviewModal({ results, loading, onClose }) {
  if (results === null) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80" onClick={onClose}>
      <div className="bg-gray-900 rounded-xl border border-gray-700 p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-white">🔍 Preview — 3 random items</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl leading-none">✕</button>
        </div>

        {loading && results.length === 0 && (
          <div className="text-center text-gray-400 py-12">Fetching ratings & rendering posters…</div>
        )}

        {!loading && results.length === 0 && (
          <div className="text-center text-gray-400 py-12">No results — library may have no rated items with matching sources.</div>
        )}

        <div className="grid grid-cols-3 gap-5">
          {results.map((item, i) => (
            <div key={i} className="flex flex-col items-center gap-2">
              <img
                src={`data:image/jpeg;base64,${item.image}`}
                alt={item.title}
                className="rounded-lg w-full object-cover shadow-lg"
              />
              <div className="text-center">
                <div className="text-sm font-medium text-white truncate w-full">{item.title} {item.year && <span className="text-gray-400">({item.year})</span>}</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {Object.entries(item.ratings).map(([k, v]) => `${k.toUpperCase()}: ${v}`).join(' · ')}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
