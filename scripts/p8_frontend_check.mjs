// Credential-free frontend build/preview: never loads runtime .env files.
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const keep=new Set(['SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','HOMEDRIVE','HOMEPATH','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE']);
for(const key of Object.keys(process.env)) if(!keep.has(key.toUpperCase())) delete process.env[key];
const root=path.resolve('frontend');
process.chdir(root);
const {build,createServer}=await import(pathToFileURL(path.join(root,'node_modules/vite/dist/node/index.js')));
const {default:react}=await import(pathToFileURL(path.join(root,'node_modules/@vitejs/plugin-react/dist/index.js')));
const config={root,configFile:false,envDir:false,plugins:[react()],
  server:{host:'127.0.0.1',port:5173,strictPort:true,proxy:{'/api':'http://127.0.0.1:8001'}}};
if(process.argv.includes('--serve')) {
  const server=await createServer(config);await server.listen();server.printUrls();
} else await build(config);
