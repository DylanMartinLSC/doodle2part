// Three.js viewer for the generated GLBs: orbit controls, turntable spin, wireframe toggle.
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";
import { GLTFLoader } from "/static/vendor/GLTFLoader.js";

export function createViewer(container) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.append(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
  // TRELLIS models face +Z, so start from a front three-quarter view.
  const HOME = new THREE.Vector3(1.1, 0.8, 2.6);
  camera.position.copy(HOME);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x404050, 2.2));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(2, 3, 2);
  scene.add(key);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.5;
  // Grabbing the model stops the turntable so it doesn't fight the user.
  controls.addEventListener("start", () => { controls.autoRotate = false; onSpinChange?.(false); });

  const loader = new GLTFLoader();
  let model = null;
  let wireframe = false;
  let onSpinChange = null;

  function resize() {
    const { clientWidth: w, clientHeight: h } = container;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });

  function forEachMaterial(fn) {
    model?.traverse((o) => o.isMesh && fn(o.material));
  }

  async function load(url) {
    const gltf = await loader.loadAsync(url);
    if (model) {
      scene.remove(model);
      model.traverse((o) => { if (o.isMesh) { o.geometry.dispose(); o.material.dispose(); } });
    }
    model = gltf.scene;
    let faces = 0;
    model.traverse((o) => {
      if (!o.isMesh) return;
      if (!o.geometry.attributes.normal) o.geometry.computeVertexNormals();
      faces += (o.geometry.index?.count ?? o.geometry.attributes.position.count) / 3;
      // glTF's default material is fully metallic, which renders vertex colours almost black.
      o.material = new THREE.MeshStandardMaterial({
        vertexColors: !!o.geometry.attributes.color,
        color: o.geometry.attributes.color ? 0xffffff : 0xb8c4e0,
        roughness: 0.75,
        metalness: 0,
        wireframe,
      });
    });

    // Centre the model and scale it to a unit-ish size so every result frames the same way.
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3()).length();
    model.position.sub(box.getCenter(new THREE.Vector3()));
    const wrapper = new THREE.Group();
    wrapper.add(model);
    wrapper.scale.setScalar(2 / size);
    scene.add(wrapper);
    model = wrapper;
    // The turntable may have spun the empty scene while the model was building; start each model facing front.
    controls.target.set(0, 0, 0);
    camera.position.copy(HOME);
    controls.update();
    return { faces: Math.round(faces) };
  }

  return {
    load,
    setWireframe(on) { wireframe = on; forEachMaterial((m) => (m.wireframe = on)); },
    setSpin(on) { controls.autoRotate = on; },
    // Place the camera at `radians` around the vertical axis from the home view (used by scripts/record_demo.py).
    orbitTo(radians) {
      controls.autoRotate = false;
      camera.position.copy(HOME).applyAxisAngle(new THREE.Vector3(0, 1, 0), radians);
      camera.lookAt(controls.target);
      controls.update();
    },
    onSpinChange(fn) { onSpinChange = fn; },
  };
}
