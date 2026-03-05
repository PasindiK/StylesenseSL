/// <reference types="vite/client" />

declare module './modules/data_mesh/src/App.jsx' {
  import type { ComponentType } from 'react'
  const DataMeshApp: ComponentType<any>
  export default DataMeshApp
}
