<script setup lang="ts">
import { onBeforeUnmount, onMounted, useTemplateRef } from 'vue'
import * as THREE from 'three'
import { countryFeature } from '@/lib/data'
import type { GlobePoint } from '@/lib/types'

const props = defineProps<{
  points: GlobePoint[]
  reducedMotion: boolean
}>()

const container = useTemplateRef<HTMLDivElement>('container')

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let globe: THREE.Group | null = null
let fireMaterial: THREE.PointsMaterial | null = null
let haloMaterial: THREE.PointsMaterial | null = null
let stars: THREE.Points | null = null
let satellites: { mesh: THREE.Mesh; radius: number; speed: number; phase: number; tilt: number }[] = []
let resizeObserver: ResizeObserver | null = null
let visibilityObserver: IntersectionObserver | null = null
let raf = 0
let visible = true
let disposed = false
let pointer = { x: 0, y: 0 }
let targetPointer = { x: 0, y: 0 }
let scrollProgress = 0
let targetScroll = 0
let clock: THREE.Clock | null = null

const R = 1

function lonLatToVector3(lon: number, lat: number, radius = R): THREE.Vector3 {
  const phi = ((90 - lat) * Math.PI) / 180
  const theta = ((lon + 180) * Math.PI) / 180
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  )
}

function makeGlowTexture(): THREE.CanvasTexture {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(0.25, 'rgba(255,220,150,0.95)')
  gradient.addColorStop(0.55, 'rgba(255,122,61,0.45)')
  gradient.addColorStop(1, 'rgba(255,94,26,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, size, size)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

function createGraticule(): THREE.Group {
  const group = new THREE.Group()
  const material = new THREE.LineBasicMaterial({
    color: 0x2f7b89,
    transparent: true,
    opacity: 0.16,
    depthWrite: false,
  })

  for (let lat = -60; lat <= 60; lat += 30) {
    const points: THREE.Vector3[] = []
    for (let lon = -180; lon <= 180; lon += 4) {
      points.push(lonLatToVector3(lon, lat, R * 1.002))
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    group.add(new THREE.Line(geometry, material))
  }

  for (let lon = -180; lon < 180; lon += 30) {
    const points: THREE.Vector3[] = []
    for (let lat = -90; lat <= 90; lat += 4) {
      points.push(lonLatToVector3(lon, lat, R * 1.002))
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    group.add(new THREE.Line(geometry, material))
  }

  return group
}

function createAtmosphere(): THREE.Mesh {
  const geometry = new THREE.SphereGeometry(R * 1.16, 64, 64)
  const material = new THREE.ShaderMaterial({
    vertexShader: `
      varying vec3 vNormal;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      void main() {
        float intensity = pow(0.62 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.4);
        vec3 color = mix(vec3(0.10, 0.75, 0.72), vec3(0.95, 0.36, 0.12), 0.18);
        gl_FragColor = vec4(color, 1.0) * intensity;
      }
    `,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false,
  })
  return new THREE.Mesh(geometry, material)
}

function createGabonOutline(): THREE.Group {
  const group = new THREE.Group()
  const ga = countryFeature.value
  if (!ga) return group
  const material = new THREE.LineBasicMaterial({
    color: 0x8ef7e4,
    transparent: true,
    opacity: 0.95,
    depthWrite: false,
  })
  const glowMaterial = new THREE.LineBasicMaterial({
    color: 0xffb347,
    transparent: true,
    opacity: 0.35,
    depthWrite: false,
  })

  const polygons = ga.geometry.coordinates
  for (const polygon of polygons) {
    for (const ring of polygon) {
      const points = ring.map(([lon, lat]) => lonLatToVector3(lon, lat, R * 1.012))
      const geometry = new THREE.BufferGeometry().setFromPoints(points)
      group.add(new THREE.Line(geometry, material))
      const glowGeometry = new THREE.BufferGeometry().setFromPoints(
        ring.map(([lon, lat]) => lonLatToVector3(lon, lat, R * 1.017)),
      )
      group.add(new THREE.Line(glowGeometry, glowMaterial))
    }
  }

  // Marqueur central : un petit sprite lumineux sur le pays.
  const marker = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: makeGlowTexture(),
      color: 0xffb347,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      opacity: 0.9,
    }),
  )
  marker.position.copy(lonLatToVector3(11.7, -0.8, R * 1.03))
  marker.scale.setScalar(0.075)
  group.add(marker)

  return group
}

function createOrbits(): THREE.Group {
  const group = new THREE.Group()
  const configs = [
    { radius: 1.34, tilt: 0.5, color: 0x5eead4, speed: 0.32, phase: 0 },
    { radius: 1.55, tilt: -0.7, color: 0xff7a3d, speed: 0.22, phase: 2.1 },
  ]
  for (const config of configs) {
    const points: THREE.Vector3[] = []
    for (let i = 0; i <= 220; i++) {
      const angle = (i / 220) * Math.PI * 2
      const x = Math.cos(angle) * config.radius
      const z = Math.sin(angle) * config.radius
      const y = Math.sin(angle) * config.radius * Math.sin(config.tilt)
      const zz = z * Math.cos(config.tilt)
      points.push(new THREE.Vector3(x, y, zz))
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    const material = new THREE.LineBasicMaterial({
      color: config.color,
      transparent: true,
      opacity: 0.16,
      depthWrite: false,
    })
    group.add(new THREE.LineLoop(geometry, material))

    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.014, 12, 12),
      new THREE.MeshBasicMaterial({ color: config.color }),
    )
    group.add(mesh)
    satellites.push({
      mesh,
      radius: config.radius,
      speed: config.speed,
      phase: config.phase,
      tilt: config.tilt,
    })
  }
  return group
}

function createFirePoints(): THREE.Group {
  const group = new THREE.Group()
  const texture = makeGlowTexture()
  const positions = new Float32Array(props.points.length * 3)
  const colors = new Float32Array(props.points.length * 3)
  const colorA = new THREE.Color(0xff5e1a)
  const colorB = new THREE.Color(0xffe0a3)
  const maxWeight = Math.max(...props.points.map((p) => p.weight), 1)

  props.points.forEach((point, index) => {
    const v = lonLatToVector3(point.lon, point.lat, R * 1.006)
    positions[index * 3] = v.x
    positions[index * 3 + 1] = v.y
    positions[index * 3 + 2] = v.z
    const t = Math.min(1, Math.sqrt(point.weight / maxWeight))
    const color = colorA.clone().lerp(colorB, t)
    colors[index * 3] = color.r
    colors[index * 3 + 1] = color.g
    colors[index * 3 + 2] = color.b
  })

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))

  fireMaterial = new THREE.PointsMaterial({
    size: 0.024,
    map: texture,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
    opacity: 0.95,
  })
  group.add(new THREE.Points(geometry, fireMaterial))

  const haloGeometry = geometry.clone()
  haloMaterial = new THREE.PointsMaterial({
    size: 0.075,
    map: texture,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
    opacity: 0.16,
  })
  group.add(new THREE.Points(haloGeometry, haloMaterial))

  return group
}

function createStars(): THREE.Points {
  const count = 1400
  const positions = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const radius = 7 + Math.random() * 14
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = radius * Math.cos(phi)
    positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta)
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const material = new THREE.PointsMaterial({
    size: 0.018,
    color: 0x9fb4c8,
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  return new THREE.Points(geometry, material)
}

function onPointerMove(event: PointerEvent) {
  targetPointer.x = (event.clientX / window.innerWidth - 0.5) * 2
  targetPointer.y = (event.clientY / window.innerHeight - 0.5) * 2
}

function onScroll() {
  const max = window.innerHeight * 1.25
  targetScroll = Math.min(1, Math.max(0, window.scrollY / max))
}

function updateSatellites(time: number) {
  for (const satellite of satellites) {
    const angle = time * satellite.speed + satellite.phase
    const x = Math.cos(angle) * satellite.radius
    const z = Math.sin(angle) * satellite.radius
    const y = Math.sin(angle) * satellite.radius * Math.sin(satellite.tilt)
    satellite.mesh.position.set(x, y, z * Math.cos(satellite.tilt))
  }
}

function render() {
  if (!renderer || !scene || !camera || !globe || disposed) return
  clock ??= new THREE.Clock()
  const elapsed = clock.getElapsedTime()

  pointer.x += (targetPointer.x - pointer.x) * 0.045
  pointer.y += (targetPointer.y - pointer.y) * 0.045
  scrollProgress += (targetScroll - scrollProgress) * 0.045

  if (!props.reducedMotion) {
    // Le Gabon doit faire face à la caméra : rotation de base -90° autour de Y.
    globe.rotation.y =
      -Math.PI / 2 + Math.sin(elapsed * 0.08) * 0.045 + pointer.x * 0.09 + scrollProgress * 0.35
    globe.rotation.x = -0.16 + pointer.y * 0.05 + scrollProgress * 0.03
    camera.position.z = 3.25 - scrollProgress * 0.55
    camera.position.y = 0.12 + pointer.y * 0.06
    camera.lookAt(0, 0, 0)
    if (fireMaterial) fireMaterial.opacity = 0.82 + Math.sin(elapsed * 1.6) * 0.1
    if (haloMaterial) haloMaterial.opacity = 0.1 + Math.sin(elapsed * 1.1 + 1) * 0.03
    updateSatellites(elapsed)
    if (stars) stars.rotation.y = elapsed * 0.006
  }

  renderer.render(scene, camera)
  if (!props.reducedMotion && visible) raf = requestAnimationFrame(render)
}

function resize() {
  if (!renderer || !camera || !container.value) return
  const width = container.value.clientWidth
  const height = container.value.clientHeight
  if (!width || !height) return
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

onMounted(() => {
  const el = container.value
  if (!el) return

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
  camera.position.set(0, 0.12, 3.25)

  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance',
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x000000, 0)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  el.appendChild(renderer.domElement)

  scene.add(new THREE.AmbientLight(0x9ec4d8, 2.1))
  const key = new THREE.DirectionalLight(0xffb37a, 2.6)
  key.position.set(-3, 2, 4)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0x5eead4, 1.6)
  rim.position.set(3, -1, -3)
  scene.add(rim)

  globe = new THREE.Group()
  scene.add(globe)

  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(R, 64, 64),
    new THREE.MeshStandardMaterial({
      color: 0x0b2230,
      roughness: 0.72,
      metalness: 0.18,
      emissive: 0x07202a,
      emissiveIntensity: 1.2,
    }),
  )
  globe.add(sphere)

  const wire = new THREE.Mesh(
    new THREE.SphereGeometry(R * 1.001, 32, 16),
    new THREE.MeshBasicMaterial({
      color: 0x2f7b89,
      wireframe: true,
      transparent: true,
      opacity: 0.08,
      depthWrite: false,
    }),
  )
  globe.add(wire)
  globe.add(createGraticule())
  globe.add(createAtmosphere())
  globe.add(createGabonOutline())
  globe.add(createFirePoints())
  globe.add(createOrbits())

  stars = createStars()
  scene.add(stars)

  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(el)
  resize()

  visibilityObserver = new IntersectionObserver(
    ([entry]) => {
      visible = entry?.isIntersecting ?? false
      if (visible && !props.reducedMotion) {
        cancelAnimationFrame(raf)
        raf = requestAnimationFrame(render)
      }
    },
    { threshold: 0.01 },
  )
  visibilityObserver.observe(el)

  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('scroll', onScroll, { passive: true })

  if (props.reducedMotion) {
    render()
  } else {
    raf = requestAnimationFrame(render)
  }
})

onBeforeUnmount(() => {
  disposed = true
  cancelAnimationFrame(raf)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('scroll', onScroll)
  resizeObserver?.disconnect()
  visibilityObserver?.disconnect()
  scene?.traverse((object) => {
    const mesh = object as THREE.Mesh
    mesh.geometry?.dispose()
    const material = mesh.material
    if (Array.isArray(material)) material.forEach((m) => m.dispose())
    else material?.dispose()
  })
  renderer?.dispose()
  if (renderer?.domElement.parentElement) {
    renderer.domElement.parentElement.removeChild(renderer.domElement)
  }
  renderer = null
  scene = null
  camera = null
  globe = null
  satellites = []
})
</script>

<template>
  <div ref="container" class="globe-canvas" aria-hidden="true"></div>
</template>

<style scoped>
.globe-canvas {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.globe-canvas :deep(canvas) {
  width: 100% !important;
  height: 100% !important;
  display: block;
}
</style>
