// @vitest-environment node
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { expect, it } from 'vitest';

// Execute the installed, unmodified DSP with real PCM blocks, not a mocked beat detector.
function analyse(signal: (time: number) => number, rate: number) {
  const beats: number[] = [];
  let Processor: any;
  const sandbox = createContext({ sampleRate: rate, currentTime: 0, console,
    AudioWorkletProcessor: class { port = { onmessage: null, postMessage(message: { type: string }) {
      if (message.type === 'beat') beats.push(Number(sandbox.currentTime));
    } }; },
    registerProcessor(_name: string, implementation: any) { Processor = implementation; },
  });
  const code = readFileSync(new URL('../node_modules/@nekopaw/tempora/dist/worklet.mjs', import.meta.url), 'utf8');
  runInContext(code.replace(/export\s*\{\s*\};?/, ''), sandbox);
  const processor = new Processor();
  processor.port.onmessage({ data: { type: 'parameters', parameters: { warmup: false, spectralFlux: false, adaptiveThreshold: false }, reset: true } });
  for (let frame = 0; frame < rate * 6; frame += 128) {
    sandbox.currentTime = frame / rate;
    const input = Float32Array.from({ length: 128 }, (_, i) => signal((frame + i) / rate));
    processor.process([[input]], [[new Float32Array(128)]]);
  }
  return beats;
}
it.each([44100, 48000])('Tempora detects PCM kick pulses at %i Hz and ignores silence', rate => {
  expect(analyse(() => 0, rate)).toEqual([]);
  const beats = analyse(time => {
    const phase = time % 0.5;
    return phase < 0.15 ? Math.sin(2 * Math.PI * 80 * time) * Math.exp(-phase * 25) * 0.9 : 0;
  }, rate);
  expect(beats.length).toBeGreaterThanOrEqual(8);
  expect(beats.length).toBeLessThanOrEqual(14);
  expect(beats.every((beat, i) => !i || beat - beats[i - 1] > 0.2)).toBe(true);
});
