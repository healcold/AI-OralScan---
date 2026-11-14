import { zh } from '../../lib/zh'
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { Asset } from '../../lib/api'
import { Button } from '../../components/ui/button'

export default function MeshViewer({asset}: {asset:Asset}) {
 const container=useRef<HTMLDivElement>(null); const controls=useRef<OrbitControls|null>(null); const meshes=useRef<THREE.Mesh[]>([]); const [wire,setWire]=useState(false); const [state,setState]=useState('正在加载三维视图…'); const [error,setError]=useState('')
 useEffect(()=>{let disposed=false; let renderer:THREE.WebGLRenderer|undefined; let animation=0; let observer:ResizeObserver|undefined; let root:THREE.Object3D|undefined; let controller:OrbitControls|undefined
  const node=container.current; if(!node)return
  async function load(){try{
   setError('');setState('正在加载三维视图…')
   const response=await fetch(`/api/scans/${asset.scan_id}/assets/${asset.asset_id}/content`);if(!response.ok)throw new Error('无法读取已保存的模型');const data=await response.arrayBuffer();if(disposed)return
   await new Promise(resolve=>setTimeout(resolve,0));if(disposed)return
   const material=()=>new THREE.MeshStandardMaterial({color:0xb9a6d4,roughness:.72,metalness:0,side:THREE.DoubleSide})
   if(asset.file_format==='stl'){const g=new STLLoader().parse(data);g.computeVertexNormals();root=new THREE.Mesh(g,material())}
   else if(asset.file_format==='ply'){const g=new PLYLoader().parse(data);if(!g.getAttribute('normal'))g.computeVertexNormals();const m=material();if(g.getAttribute('color')){m.vertexColors=true;m.color.set(0xffffff)}root=new THREE.Mesh(g,m)}
   else if(asset.file_format==='obj'){root=new OBJLoader().parse(new TextDecoder().decode(data));root.traverse(child=>{if(child instanceof THREE.Mesh){if(!child.geometry.getAttribute('normal'))child.geometry.computeVertexNormals();const old=Array.isArray(child.material)?child.material:[child.material];old.forEach(m=>m.dispose());child.material=material()}})}else throw new Error('不支持的文件格式')
   const bounds=new THREE.Box3().setFromObject(root);if(bounds.isEmpty())throw new Error('模型中没有可渲染的几何结构');const center=bounds.getCenter(new THREE.Vector3());root.position.sub(center);const size=bounds.getSize(new THREE.Vector3());const extent=Math.max(size.x,size.y,size.z);if(!Number.isFinite(extent)||extent<=0)throw new Error('模型没有有效的可见范围')
   const scene=new THREE.Scene();scene.background=new THREE.Color('#f7f5f9');scene.add(root);scene.add(new THREE.HemisphereLight(0xffffff,0x9cb4be,2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(4,6,8);scene.add(light)
   const camera=new THREE.PerspectiveCamera(45,1,Math.max(extent/1000,.00001),extent*100);camera.position.set(extent*1.7,extent*1.3,extent*1.7);camera.lookAt(0,0,0)
   renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));node!.appendChild(renderer.domElement);controller=new OrbitControls(camera,renderer.domElement);controls.current=controller;controller.enableDamping=true;controller.target.set(0,0,0);controller.update();controller.saveState()
   meshes.current=[];root.traverse(child=>{if(child instanceof THREE.Mesh)meshes.current.push(child)})
   const resize=()=>{if(!renderer||!node)return;const w=node.clientWidth||1,h=node.clientHeight||1;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix()};observer=new ResizeObserver(resize);observer.observe(node!);resize()
   const tick=()=>{if(disposed)return;controller?.update();renderer?.render(scene,camera);animation=requestAnimationFrame(tick)};tick();setState('')
  }catch(e){if(!disposed){setState('');setError(e instanceof Error?zh(e.message):'无法渲染模型')}}}
  void load(); return ()=>{disposed=true;cancelAnimationFrame(animation);observer?.disconnect();controller?.dispose();controls.current=null;meshes.current=[];root?.traverse(child=>{if(child instanceof THREE.Mesh){child.geometry.dispose();const materials=Array.isArray(child.material)?child.material:[child.material];materials.forEach(m=>m.dispose())}});renderer?.dispose();renderer?.domElement.remove()}
 },[asset])
 useEffect(()=>{meshes.current.forEach(mesh=>{const materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];materials.forEach(m=>{if(m instanceof THREE.MeshStandardMaterial)m.wireframe=wire})})},[wire,state])
 return <><div className="viewer" ref={container} aria-label="三维模型视图">{state&&<div className="viewer-message">{state}</div>}{error&&<div role="alert" className="viewer-message">{error}</div>}</div><div className="viewer-controls"><Button variant="outline" onClick={()=>controls.current?.reset()} disabled={!!state||!!error}>重置视角</Button><Button variant="outline" aria-pressed={wire} onClick={()=>setWire(!wire)} disabled={!!state||!!error}>{wire?'实体视图':'线框视图'}</Button><span>拖动旋转 · 滚轮缩放 · 按住右键拖动平移</span></div></>
}

