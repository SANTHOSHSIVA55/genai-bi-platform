import React, { useRef, useMemo, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float, MeshDistortMaterial, MeshWobbleMaterial, Sphere, Torus, Icosahedron, Octahedron } from '@react-three/drei';
import * as THREE from 'three';

/* ───── Floating Data Sphere ───── */
const DataSphere = ({ position = [0, 0, 0], color = '#e50914', speed = 1 }) => {
  const meshRef = useRef();
  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.3 * speed) * 0.3;
      meshRef.current.rotation.y += 0.005 * speed;
    }
  });
  return (
    <Float speed={2} rotationIntensity={0.5} floatIntensity={1}>
      <Sphere ref={meshRef} args={[1, 64, 64]} position={position}>
        <MeshDistortMaterial
          color={color}
          roughness={0.1}
          metalness={0.8}
          distort={0.3}
          speed={2}
          transparent
          opacity={0.7}
        />
      </Sphere>
    </Float>
  );
};

/* ───── Orbiting Ring ───── */
const OrbitRing = ({ radius = 2, color = '#ff3e4b', speed = 0.5, thickness = 0.03 }) => {
  const ringRef = useRef();
  useFrame((state) => {
    if (ringRef.current) {
      ringRef.current.rotation.x = Math.PI / 2 + Math.sin(state.clock.elapsedTime * speed) * 0.3;
      ringRef.current.rotation.z += 0.003;
    }
  });
  return (
    <Torus ref={ringRef} args={[radius, thickness, 16, 100]}>
      <meshStandardMaterial color={color} transparent opacity={0.6} emissive={color} emissiveIntensity={0.3} />
    </Torus>
  );
};

/* ───── Data Particles ───── */
const DataParticles = ({ count = 200 }) => {
  const pointsRef = useRef();
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 15;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 15;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 15;
    }
    return pos;
  }, [count]);

  const colors = useMemo(() => {
    const cols = new Float32Array(count * 3);
    const palette = [
      new THREE.Color('#e50914'),
      new THREE.Color('#ff3e4b'),
      new THREE.Color('#b81d24'),
      new THREE.Color('#ffa00a'),
      new THREE.Color('#ff7e8a'),
    ];
    for (let i = 0; i < count; i++) {
      const c = palette[Math.floor(Math.random() * palette.length)];
      cols[i * 3] = c.r;
      cols[i * 3 + 1] = c.g;
      cols[i * 3 + 2] = c.b;
    }
    return cols;
  }, [count]);

  useFrame((state) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y += 0.0005;
      pointsRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.1) * 0.1;
    }
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
        <bufferAttribute attach="attributes-color" count={count} array={colors} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.05} vertexColors transparent opacity={0.8} sizeAttenuation />
    </points>
  );
};

/* ───── Wireframe Icosahedron ───── */
const WireGeo = ({ position = [0, 0, 0], color = '#ff3e4b', scale = 1 }) => {
  const ref = useRef();
  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.x += 0.003;
      ref.current.rotation.y += 0.005;
      ref.current.scale.setScalar(scale + Math.sin(state.clock.elapsedTime) * 0.05);
    }
  });
  return (
    <Float speed={1.5} floatIntensity={0.5}>
      <Icosahedron ref={ref} args={[1, 1]} position={position}>
        <meshStandardMaterial color={color} wireframe transparent opacity={0.4} emissive={color} emissiveIntensity={0.2} />
      </Icosahedron>
    </Float>
  );
};

/* ───── Neural Node ───── */
const NeuralNode = ({ position, color = '#e50914' }) => {
  const ref = useRef();
  useFrame((state) => {
    if (ref.current) {
      ref.current.scale.setScalar(0.08 + Math.sin(state.clock.elapsedTime * 2 + position[0]) * 0.02);
    }
  });
  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[1, 16, 16]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} transparent opacity={0.8} />
    </mesh>
  );
};

/* ───── Floating Octahedron (AI Brain) ───── */
const AIBrain = ({ position = [0, 0, 0], scale = 1 }) => {
  const ref = useRef();
  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y += 0.008;
      ref.current.rotation.z = Math.sin(state.clock.elapsedTime * 0.5) * 0.2;
    }
  });
  return (
    <Float speed={2} rotationIntensity={0.3} floatIntensity={1.2}>
      <Octahedron ref={ref} args={[1]} position={position} scale={scale}>
        <MeshWobbleMaterial
          color="#ff7e8a"
          roughness={0.1}
          metalness={0.9}
          factor={0.2}
          speed={1.5}
          transparent
          opacity={0.6}
        />
      </Octahedron>
    </Float>
  );
};

/* ═══════ SCENE PRESETS ═══════ */

// Landing Page — big hero scene
export const HeroScene = () => (
  <Canvas
    camera={{ position: [0, 0, 8], fov: 60 }}
    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'auto' }}
    gl={{ alpha: true, antialias: true }}
  >
    <ambientLight intensity={0.3} />
    <pointLight position={[10, 10, 10]} intensity={1} color="#e50914" />
    <pointLight position={[-10, -5, 5]} intensity={0.5} color="#b81d24" />
    <spotLight position={[5, 5, 5]} angle={0.3} penumbra={1} intensity={0.8} color="#ff3e4b" />
    <Suspense fallback={null}>
      <DataSphere position={[0, 0.3, 0]} color="#e50914" speed={0.8} />
      <OrbitRing radius={2} color="#ff3e4b" speed={0.3} />
      <OrbitRing radius={2.5} color="#b81d24" speed={0.5} thickness={0.02} />
      <OrbitRing radius={3} color="#ffa00a" speed={0.2} thickness={0.01} />
      <WireGeo position={[3.5, 1.5, -2]} color="#ff7e8a" scale={0.7} />
      <WireGeo position={[-3.5, -1, -1]} color="#ffa00a" scale={0.5} />
      <AIBrain position={[-2.5, 2, -1]} scale={0.4} />
      <DataParticles count={300} />
    </Suspense>
  </Canvas>
);

// Dashboard — subtle background scene
export const DashboardScene = () => (
  <Canvas
    camera={{ position: [0, 0, 6], fov: 50 }}
    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    gl={{ alpha: true, antialias: true }}
  >
    <ambientLight intensity={0.2} />
    <pointLight position={[5, 5, 5]} intensity={0.5} color="#e50914" />
    <Suspense fallback={null}>
      <DataParticles count={150} />
      <WireGeo position={[4, 2, -3]} color="#ff3e4b" scale={0.4} />
      <WireGeo position={[-4, -2, -2]} color="#b81d24" scale={0.3} />
      <OrbitRing radius={5} color="#333333" speed={0.1} thickness={0.01} />
    </Suspense>
  </Canvas>
);

// Auth pages — elegant scene
export const AuthScene = () => (
  <Canvas
    camera={{ position: [0, 0, 6], fov: 50 }}
    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    gl={{ alpha: true, antialias: true }}
  >
    <ambientLight intensity={0.2} />
    <pointLight position={[5, 5, 5]} intensity={0.6} color="#e50914" />
    <pointLight position={[-5, -5, 5]} intensity={0.4} color="#b81d24" />
    <Suspense fallback={null}>
      <AIBrain position={[3, 1.5, -1]} scale={0.5} />
      <WireGeo position={[-3, -1.5, -2]} color="#ff3e4b" scale={0.6} />
      <DataParticles count={100} />
      <OrbitRing radius={3} color="#333333" speed={0.15} thickness={0.01} />
    </Suspense>
  </Canvas>
);

// Mini 3D widget for cards
export const MiniDataViz = ({ type = 'sphere' }) => (
  <Canvas
    camera={{ position: [0, 0, 3], fov: 50 }}
    style={{ width: '100%', height: '100%' }}
    gl={{ alpha: true, antialias: true }}
  >
    <ambientLight intensity={0.4} />
    <pointLight position={[3, 3, 3]} intensity={0.8} color="#e50914" />
    <Suspense fallback={null}>
      {type === 'sphere' && <DataSphere position={[0, 0, 0]} color="#e50914" speed={0.6} />}
      {type === 'brain' && <AIBrain position={[0, 0, 0]} scale={0.8} />}
      {type === 'wire' && <WireGeo position={[0, 0, 0]} color="#ff3e4b" scale={1} />}
      {type === 'ring' && (
        <>
          <OrbitRing radius={1} color="#ff3e4b" speed={0.5} thickness={0.03} />
          <OrbitRing radius={1.3} color="#b81d24" speed={0.3} thickness={0.02} />
        </>
      )}
    </Suspense>
  </Canvas>
);

export default HeroScene;
