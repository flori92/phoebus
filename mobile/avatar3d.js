/**
 * J.A.R.V.I.S — Avatar 3D Holographique (Shader GLSL)
 */

function createAvatar3D(canvas, imageUrl) {
  let destroyed = false;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0); // Transparent pour voir le fond CSS

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
  camera.position.z = 5;

  // ── Texture ───────────────────────────────────────────────────────────────
  const textureLoader = new THREE.TextureLoader();
  const avatarTex = textureLoader.load(imageUrl);
  
  // ── Custom Shader Material ────────────────────────────────────────────────
  const vertexShader = `
    uniform float u_time;
    uniform float u_volume;
    uniform float u_state; // 0: idle, 1: listening, 2: speaking
    varying vec2 vUv;
    varying float vWave;

    void main() {
      vUv = uv;
      vec3 pos = position;

      // Onde de choc 3D (Z-displacement) basée sur le volume et le centre
      float dist = distance(uv, vec2(0.5));
      float wave = sin(dist * 10.0 - u_time * 5.0) * u_volume * 0.5;
      
      // Respiration légère
      float breath = sin(u_time * 2.0) * 0.05 * (u_state == 0.0 ? 1.0 : 0.2);
      
      pos.z += wave + breath;
      vWave = wave;

      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }
  `;

  const fragmentShader = `
    uniform sampler2D u_tex;
    uniform float u_time;
    uniform float u_volume;
    uniform float u_state;
    varying vec2 vUv;
    varying float vWave;

    void main() {
      // Masque circulaire
      float dist = distance(vUv, vec2(0.5));
      if(dist > 0.5) discard;

      // Aberration chromatique quand il parle (basé sur le volume)
      float aberration = u_volume * 0.05;
      vec4 texR = texture2D(u_tex, vUv + vec2(aberration, 0.0));
      vec4 texG = texture2D(u_tex, vUv);
      vec4 texB = texture2D(u_tex, vUv - vec2(aberration, 0.0));
      
      vec4 color = vec4(texR.r, texG.g, texB.b, texG.a);

      // Scanline effect
      float scanline = sin(vUv.y * 100.0 - u_time * 10.0) * 0.04;
      color.rgb += scanline;

      // Glow sur les bords
      float edgeGlow = smoothstep(0.4, 0.5, dist);
      vec3 glowColor = vec3(0.0);
      
      if(u_state == 0.0) {
        glowColor = vec3(0.1, 0.5, 0.8); // Bleu repos
      } else if(u_state == 1.0) {
        glowColor = vec3(0.1, 0.8, 0.3); // Vert écoute
      } else if(u_state == 2.0) {
        glowColor = vec3(0.2, 0.8, 1.0); // Cyan parlant
      }

      color.rgb += glowColor * edgeGlow * (0.5 + u_volume * 2.0);
      
      // Assombrissement progressif vers les bords (Vignette)
      color.rgb *= smoothstep(0.5, 0.3, dist);

      gl_FragColor = color;
    }
  `;

  const uniforms = {
    u_tex: { value: avatarTex },
    u_time: { value: 0 },
    u_volume: { value: 0 },
    u_state: { value: 0 } // 0: idle, 1: listening, 2: thinking/speaking
  };

  const material = new THREE.ShaderMaterial({
    vertexShader,
    fragmentShader,
    uniforms,
    transparent: true
  });

  // Géométrie avec beaucoup de segments pour que la déformation 3D soit fluide
  const geometry = new THREE.PlaneGeometry(3, 3, 64, 64);
  const plane = new THREE.Mesh(geometry, material);
  scene.add(plane);

  // ── Particules flottantes autour ──────────────────────────────────────────
  const pGeo = new THREE.BufferGeometry();
  const pPos = new Float32Array(500 * 3);
  for(let i=0; i<500; i++) {
    const theta = Math.random() * Math.PI * 2;
    const r = 1.5 + Math.random() * 2.0;
    pPos[i*3] = r * Math.cos(theta);
    pPos[i*3+1] = r * Math.sin(theta);
    pPos[i*3+2] = (Math.random() - 0.5) * 2.0;
  }
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  const pMat = new THREE.PointsMaterial({ color: 0x4ca8e8, size: 0.03, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending });
  const particles = new THREE.Points(pGeo, pMat);
  scene.add(particles);

  // ── Animation Loop ────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  let state = "idle";
  let currentVolume = 0;
  let targetVolume = 0;

  let mouseX = 0;
  let mouseY = 0;
  
  // Parallaxe souris/touch
  window.addEventListener("mousemove", (e) => {
    mouseX = (e.clientX / window.innerWidth) * 2 - 1;
    mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
  });

  function animate() {
    if (destroyed) return;
    requestAnimationFrame(animate);

    const time = clock.getElapsedTime();
    uniforms.u_time.value = time;

    // Lissage du volume
    currentVolume += (targetVolume - currentVolume) * 0.15;
    uniforms.u_volume.value = currentVolume;

    // Mise à jour de l'état
    if (state === "idle") uniforms.u_state.value = 0.0;
    else if (state === "listening") uniforms.u_state.value = 1.0;
    else if (state === "speaking") uniforms.u_state.value = 2.0;
    else uniforms.u_state.value = 2.0; // thinking

    // Parallaxe de l'image
    plane.rotation.y += (mouseX * 0.3 - plane.rotation.y) * 0.05;
    plane.rotation.x += (-mouseY * 0.3 - plane.rotation.x) * 0.05;

    // Rotation lente des particules
    particles.rotation.z = time * 0.1;
    particles.rotation.y = time * 0.05;
    
    // Les particules réagissent au son
    const pScale = 1.0 + currentVolume * 2.0;
    particles.scale.set(pScale, pScale, pScale);

    if (state === "listening") pMat.color.setHex(0x22c55e);
    else if (state === "speaking") pMat.color.setHex(0x0ea5e9);
    else if (state === "thinking") pMat.color.setHex(0xf59e0b);
    else pMat.color.setHex(0x4ca8e8);

    renderer.render(scene, camera);
  }

  function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }

  window.addEventListener("resize", onResize);
  animate();

  return {
    setState(s) {
      state = s;
      if (s !== "speaking") targetVolume = 0;
    },
    setVolume(v) {
      targetVolume = v;
    },
    triggerDemo() {
      // Not implemented for this avatar
    },
    destroy() {
      destroyed = true;
      window.removeEventListener("resize", onResize);
      renderer.dispose();
    },
  };
}
