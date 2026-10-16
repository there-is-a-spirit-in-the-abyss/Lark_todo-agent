import React from 'react';
import { createRoot } from 'react-dom/client';
import { ReactFlowProvider } from '@xyflow/react';
import App from './App.jsx';
import {LocaleProvider} from './locale.jsx';
import '@xyflow/react/dist/style.css';
import '@fontsource-variable/noto-sans-sc';
import './style.css';
createRoot(document.getElementById('root')).render(<LocaleProvider><ReactFlowProvider><App /></ReactFlowProvider></LocaleProvider>);
