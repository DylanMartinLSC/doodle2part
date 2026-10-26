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
  camera.position.set(1.6, 1.0, 2.2);
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
    controls.target.set(0, 0, 0);
    return { faces: Math.round(faces) };
  }

  return {
    load,
    setWireframe(on) { wireframe = on; forEachMaterial((m) => (m.wireframe = on)); },
    setSpin(on) { controls.autoRotate = on; },
    onSpinChange(fn) { onSpinChange = fn; },
  };
}
