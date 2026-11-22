export const cueDefaults = {
  buzzer: { toneHz: 1000, cadenceBpm: 90 },
  haptics: { levelPercent: 40, cadenceBpm: 90 },
};

function within(value, [min, max]) {
  return Math.min(max, Math.max(min, value));
}

export function buzzerPreset(caps) {
  const limits = caps?.buzzerLimits;
  if (!caps?.buzzerSupported || !limits?.toneHz || !limits.cadenceBpm)
    return null;
  return {
    toneHz: within(cueDefaults.buzzer.toneHz, limits.toneHz),
    cadenceBpm: within(cueDefaults.buzzer.cadenceBpm, limits.cadenceBpm),
  };
}

export function hapticsPreset(caps) {
  const limits = caps?.hapticsLimits;
  if (!caps?.hapticsSupported || !limits?.levelsPercent?.length || !limits.cadenceBpm)
    return null;
  const { cadenceBpm, levelsPercent } = limits;
  const target = cueDefaults.haptics.levelPercent;
  const [levelPercent] = [...levelsPercent].sort(
    (a, b) => Math.abs(a - target) - Math.abs(b - target) || a - b,
  );
  return {
    levelPercent,
    cadenceBpm: within(cueDefaults.haptics.cadenceBpm, cadenceBpm),
  };
}
