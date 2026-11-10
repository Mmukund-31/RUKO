// AudioWorklet: forwards mono Float32 samples from its input to the main thread.
// The AudioContext runs at 16 kHz, so the browser has already resampled.
class PcmTap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch && ch.length) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('pcm-tap', PcmTap);
