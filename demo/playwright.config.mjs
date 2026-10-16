import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./tests/browser',
  timeout:30000,
  workers:1,
  use:{baseURL:'http://127.0.0.1:8787',viewport:{width:1440,height:950},screenshot:'only-on-failure',trace:'retain-on-failure',launchOptions:{args:['--no-sandbox']}},
  reporter:'list',
});
