import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./tests',timeout:30000,workers:1,reporter:'list',
  use:{baseURL:'http://127.0.0.1:8793',viewport:{width:1440,height:950},
    screenshot:'only-on-failure',launchOptions:{args:['--no-sandbox']}},
  webServer:{command:'node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 8793 --strictPort',
    url:'http://127.0.0.1:8793/team/oc_test',reuseExistingServer:false},
});
