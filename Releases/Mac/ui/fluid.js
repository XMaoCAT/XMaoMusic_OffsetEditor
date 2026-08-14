(function () {
  "use strict";

  const canvas = document.getElementById("fluidCanvas");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const gl = canvas.getContext("webgl", {
    alpha: false,
    antialias: false,
    powerPreference: "low-power",
  });

  const state = {
    enabled: localStorage.getItem("xmao-motion") !== "off" && !reduceMotion.matches,
    theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
    themeMix: document.documentElement.dataset.theme === "light" ? 1 : 0,
    targetThemeMix: document.documentElement.dataset.theme === "light" ? 1 : 0,
    energy: 0.22,
    targetEnergy: 0.22,
    direction: -0.35,
    targetDirection: -0.35,
    startedAt: performance.now(),
    frame: 0,
  };

  function resizeCanvas() {
    const scale = Math.min(window.devicePixelRatio || 1, 1.5);
    const width = Math.max(1, Math.floor(window.innerWidth * scale));
    const height = Math.max(1, Math.floor(window.innerHeight * scale));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      if (gl) gl.viewport(0, 0, width, height);
    }
  }

  function fallback() {
    const context = canvas.getContext("2d");
    if (!context) return;
    resizeCanvas();
    const gradient = context.createLinearGradient(0, 0, canvas.width, canvas.height);
    const light = state.theme === "light";
    gradient.addColorStop(0, light ? "#d8ecff" : "#05040a");
    gradient.addColorStop(0.46, light ? "#f8fbff" : "#0a0712");
    gradient.addColorStop(0.78, light ? "#b9d9f6" : "#281342");
    gradient.addColorStop(1, light ? "#edf7ff" : "#4a1f68");
    context.fillStyle = gradient;
    context.fillRect(0, 0, canvas.width, canvas.height);
  }

  if (!gl) {
    fallback();
    window.fluidBackground = {
      setMode() {},
      setProgress() {},
      setEnabled() {},
      setTheme(theme) {
        state.theme = theme === "light" ? "light" : "dark";
        fallback();
      },
      isEnabled: () => false,
    };
    return;
  }

  const vertexSource = `
    attribute vec2 position;
    void main() {
      gl_Position = vec4(position, 0.0, 1.0);
    }
  `;

  const fragmentSource = `
    precision highp float;
    uniform vec2 resolution;
    uniform float time;
    uniform float energy;
    uniform float direction;
    uniform float themeMix;

    float hash(vec2 p) {
      return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
    }

    float noise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(
        mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
        mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
        u.y
      );
    }

    float fbm(vec2 p) {
      float value = 0.0;
      float amplitude = 0.52;
      for (int octave = 0; octave < 4; octave++) {
        value += amplitude * noise(p);
        p = mat2(1.62, 1.18, -1.18, 1.62) * p + 0.17;
        amplitude *= 0.48;
      }
      return value;
    }

    void main() {
      vec2 uv = gl_FragCoord.xy / resolution.xy;
      vec2 p = uv - 0.5;
      p.x *= resolution.x / max(resolution.y, 1.0);

      float t = time * (0.035 + energy * 0.04);
      vec2 drift = vec2(direction * t, t * 0.42);
      float warpA = fbm(p * 1.55 + drift);
      float warpB = fbm(p * 2.25 - drift * 0.72 + vec2(warpA, -warpA));
      float bands = sin((p.x * 2.4 + p.y * 1.4 + warpA * 1.8 + warpB) * 3.0 - t * 1.2);
      bands = smoothstep(-0.82, 0.92, bands);

      vec3 darkBase = vec3(0.012, 0.009, 0.022);
      vec3 darkDeep = vec3(0.075, 0.026, 0.135);
      vec3 darkCyan = vec3(0.32, 0.09, 0.48);
      vec3 darkMist = vec3(0.58, 0.25, 0.72);
      vec3 lightBase = vec3(0.94, 0.975, 1.0);
      vec3 lightDeep = vec3(0.68, 0.84, 0.97);
      vec3 lightCyan = vec3(0.24, 0.58, 0.91);
      vec3 lightMist = vec3(0.99, 0.995, 1.0);
      vec3 base = mix(darkBase, lightBase, themeMix);
      vec3 deep = mix(darkDeep, lightDeep, themeMix);
      vec3 cyan = mix(darkCyan, lightCyan, themeMix);
      vec3 mist = mix(darkMist, lightMist, themeMix);
      float field = clamp(warpA * 0.58 + warpB * 0.52 + bands * 0.25, 0.0, 1.0);
      vec3 color = mix(base, deep, field);
      color = mix(color, cyan, smoothstep(0.57, 1.04, field) * (0.24 + energy * 0.16));

      float mistField = smoothstep(0.2, 0.88, warpB + warpA * 0.34);
      mistField *= smoothstep(0.86, 0.18, distance(uv, vec2(0.18, 0.82)));
      color = mix(color, mist, mistField * mix(0.2, 0.36, themeMix));

      float vignette = smoothstep(0.96, 0.25, length(p * vec2(0.7, 1.0)));
      color *= mix(0.6 + vignette * 0.42, 0.88 + vignette * 0.14, themeMix);
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  function createShader(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || "Shader compilation failed");
    }
    return shader;
  }

  let program;
  try {
    program = gl.createProgram();
    gl.attachShader(program, createShader(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, createShader(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "Shader linking failed");
    }
  } catch (error) {
    console.warn("Fluid background disabled:", error);
    fallback();
    return;
  }

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  gl.useProgram(program);
  const position = gl.getAttribLocation(program, "position");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const resolutionLocation = gl.getUniformLocation(program, "resolution");
  const timeLocation = gl.getUniformLocation(program, "time");
  const energyLocation = gl.getUniformLocation(program, "energy");
  const directionLocation = gl.getUniformLocation(program, "direction");
  const themeLocation = gl.getUniformLocation(program, "themeMix");

  function render(now) {
    resizeCanvas();
    state.energy += (state.targetEnergy - state.energy) * 0.035;
    state.direction += (state.targetDirection - state.direction) * 0.035;
    state.themeMix += (state.targetThemeMix - state.themeMix) * 0.08;
    const seconds = state.enabled ? (now - state.startedAt) / 1000 : 14.0;
    gl.uniform2f(resolutionLocation, canvas.width, canvas.height);
    gl.uniform1f(timeLocation, seconds);
    gl.uniform1f(energyLocation, state.energy);
    gl.uniform1f(directionLocation, state.direction);
    gl.uniform1f(themeLocation, state.themeMix);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    if (state.enabled) state.frame = requestAnimationFrame(render);
  }

  function setEnabled(enabled) {
    state.enabled = Boolean(enabled) && !reduceMotion.matches;
    localStorage.setItem("xmao-motion", state.enabled ? "on" : "off");
    cancelAnimationFrame(state.frame);
    state.startedAt = performance.now();
    state.frame = requestAnimationFrame(render);
  }

  function setMode(mode) {
    state.targetDirection = mode === "prepend" ? 0.58 : mode === "convert" ? 0.08 : -0.42;
    state.targetEnergy = mode === "prepend" ? 0.34 : mode === "convert" ? 0.3 : 0.24;
  }

  function setProgress(progress) {
    const normalized = Math.max(0, Math.min(1, Number(progress) / 100));
    state.targetEnergy = 0.25 + normalized * 0.7;
  }

  function setTheme(theme) {
    state.theme = theme === "light" ? "light" : "dark";
    state.targetThemeMix = state.theme === "light" ? 1 : 0;
    if (!state.enabled) {
      cancelAnimationFrame(state.frame);
      state.frame = requestAnimationFrame(render);
    }
  }

  window.addEventListener("resize", resizeCanvas);
  reduceMotion.addEventListener("change", () => setEnabled(localStorage.getItem("xmao-motion") !== "off"));
  window.fluidBackground = {
    setMode,
    setProgress,
    setEnabled,
    setTheme,
    isEnabled: () => state.enabled,
  };
  state.frame = requestAnimationFrame(render);
})();
