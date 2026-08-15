# XMaoMusic OffsetEditor Design System

## Surface

Operate-mode desktop audio workbench. The first task is to inspect one local
audio file, locate its timing boundary, preview that boundary, and export a
non-destructive result. The waveform is the primary visual proof, not a
decorative illustration.

## Direction

- World: precise, fluid, restrained audio tooling.
- Material: layered liquid glass over a dark or light studio field. Blur and
  translucency separate work zones, while borders stay quiet and readable.
- Wallpaper: continuous blue-white mist in light mode and restrained black-
  purple refraction in dark mode. It never competes with the waveform.
- Signature: cyan editing marker plus a draggable red playback head with a
  diamond grip. The red head is the only persistent playback accent.
- Motion: the fluid background is optional and reduced under the system motion
  preference. Control transitions use short ease-out transforms and opacity.

## Tokens

- Base spacing: 4px increments, with 8px control gaps and 12-20px workbench
  padding.
- Radius: 5px controls, 6px panels, no decorative nested card stacks.
- Window: 10px native corners on Windows in normal state, removed when
  maximized; macOS keeps native window chrome and system corner behavior.
- Accent: cyan for focus and audio state; blue for primary actions; red for
  playback position and destructive/error states.
- Depth: quiet 1px separators, inset highlights, and soft offset shadows on
  glass surfaces. No hard block shadows.
- Typography: native system sans for UI copy; tabular numerals for durations,
  BPM, offsets, and file parameters. Compact helper text remains at least 10px
  with WCAG AA contrast.

## Interaction Contract

- Clicking or dragging the waveform seeks the playback head.
- Space toggles play/pause when the waveform is focused; arrow keys seek by
  1 second, Shift plus an arrow seeks by 10 seconds.
- The preview control starts at the current trim offset. For prepend-silence
  mode it starts at the source beginning.
- Pointer up, pointer cancel, and lost pointer capture all clear scrubbing and
  commit the last safe position.
- Switching files stops playback. Background audio analysis and encoding jobs
  are serialized to protect the source file and Qt lifecycle.
- BPM analysis starts only from its dedicated command after import. Its dialog
  exposes decoding, feature extraction, segment analysis, and result stages;
  it then reports an estimated BPM, confidence, local tempo sections, and
  half/double-time candidates rather than presenting one unexplained value.

## Layout Contract

- Two-column workbench: waveform and task controls on the left, output
  parameters on the right.
- Preserve usable controls at 900x620, 1180x760, and 1440x900 desktop viewports.
- Keep native macOS chrome and the custom Windows drag region outside the HTML
  interaction layer.
