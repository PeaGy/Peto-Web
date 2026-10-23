import { defineConfig } from '@playwright/test';
import base from './playwright.config';

const channel = process.env.PETO_PLAYER_BROWSER;
if (channel && !['chrome', 'msedge'].includes(channel)) throw new Error('PETO_PLAYER_BROWSER nhận chrome hoặc msedge.');
export default defineConfig({ ...base,
  testMatch: ['companion-player.spec.ts', 'companion-player-library.spec.ts', 'player-discovery.spec.ts', 'player-library-acceptance.spec.ts'],
  projects: base.projects?.map(project => ({ ...project, use: { ...project.use, ...(channel ? { channel } : {}) } })),
});
