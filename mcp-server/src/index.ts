#!/usr/bin/env node
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { createServer } from './server.js';

// stdout 是 MCP 的通訊管道，所有 log 一律寫到 stderr。
serveStdio(() => createServer(), {
  onerror: (error) => console.error('[stockmind] transport error', error),
});
console.error('[stockmind] MCP server 已啟動（stdio）');
