#!/usr/bin/env bun
/**
 * ============================================================
 * diagram-indexer: 流程图精确索引工具
 * ============================================================
 *
 * 功能：增量解析 Mermaid 和 Canvas 文件，构建节点级索引
 * 用法：bun index.ts <目录> [--incremental] [--output <file>]
 */

import { readdir, stat, readFile, writeFile } from 'fs/promises';
import { join, extname } from 'path';

// ==================== 类型定义 ====================

interface DiagramInfo {
  type: string;
  line: number;
  participants?: string[];
  nodes?: string[];
  messages?: number;
}

interface FileIndex {
  mtime: number;
  type: 'mermaid' | 'canvas';
  diagrams?: DiagramInfo[];
  nodes?: string[];
  edges?: Array<{ from: string; to: string }>;
}

interface IndexData {
  version: string;
  updated: string;
  files: Record<string, FileIndex>;
}

// ==================== Mermaid 解析 ====================

function extractMermaidBlocks(content: string): Array<{ code: string; line: number }> {
  const blocks: Array<{ code: string; line: number }> = [];
  const regex = /```mermaid\n([\s\S]*?)```/g;
  let match;

  while ((match = regex.exec(content)) !== null) {
    const beforeMatch = content.slice(0, match.index);
    const line = beforeMatch.split('\n').length;
    blocks.push({ code: match[1], line });
  }

  return blocks;
}

function parseMermaidDiagram(code: string): DiagramInfo {
  const lines = code.trim().split('\n');
  const firstLine = lines[0].trim();

  // 识别图表类型
  let type = 'unknown';
  if (firstLine.startsWith('sequenceDiagram')) type = 'sequenceDiagram';
  else if (firstLine.startsWith('flowchart') || firstLine.startsWith('graph')) type = 'flowchart';
  else if (firstLine.startsWith('classDiagram')) type = 'classDiagram';
  else if (firstLine.startsWith('stateDiagram')) type = 'stateDiagram';
  else if (firstLine.startsWith('erDiagram')) type = 'erDiagram';
  else if (firstLine.startsWith('gantt')) type = 'gantt';

  const info: DiagramInfo = { type, line: 0 };

  // 提取参与者 (sequenceDiagram)
  if (type === 'sequenceDiagram') {
    const participants = new Set<string>();
    const participantRegex = /participant\s+(\w+)/g;
    let m;
    while ((m = participantRegex.exec(code)) !== null) {
      participants.add(m[1]);
    }
    // 也从消息中提取
    const messageRegex = /(\w+)\s*->>?\+?\s*(\w+)/g;
    while ((m = messageRegex.exec(code)) !== null) {
      participants.add(m[1]);
      participants.add(m[2]);
    }
    info.participants = Array.from(participants);
    info.messages = (code.match(/->>?/g) || []).length;
  }

  // 提取节点 (flowchart)
  if (type === 'flowchart') {
    const nodes = new Set<string>();
    const nodeRegex = /(\w+)[\[\(\{]/g;
    let m;
    while ((m = nodeRegex.exec(code)) !== null) {
      nodes.add(m[1]);
    }
    info.nodes = Array.from(nodes);
  }

  return info;
}

// ==================== Canvas 解析 ====================

interface CanvasNode {
  id: string;
  type: string;
  text?: string;
  file?: string;
  url?: string;
}

interface CanvasEdge {
  id: string;
  fromNode: string;
  toNode: string;
}

interface CanvasData {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}

function parseCanvas(content: string): { nodes: string[]; edges: Array<{ from: string; to: string }> } {
  const data: CanvasData = JSON.parse(content);
  return {
    nodes: data.nodes.map(n => n.id),
    edges: data.edges.map(e => ({ from: e.fromNode, to: e.toNode }))
  };
}

// ==================== 文件扫描 ====================

async function scanDirectory(dir: string): Promise<string[]> {
  const files: string[] = [];

  async function scan(currentDir: string) {
    const entries = await readdir(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await scan(fullPath);
      } else {
        const ext = extname(entry.name);
        if (ext === '.md' || ext === '.canvas') {
          files.push(fullPath);
        }
      }
    }
  }

  await scan(dir);
  return files;
}

// ==================== 主逻辑 ====================

async function buildIndex(
  dir: string,
  existingIndex?: IndexData,
  incremental: boolean = false
): Promise<IndexData> {
  const files = await scanDirectory(dir);
  const index: IndexData = {
    version: '1.0',
    updated: new Date().toISOString(),
    files: existingIndex?.files || {}
  };

  let processed = 0;
  let skipped = 0;

  for (const file of files) {
    const fileStat = await stat(file);
    const mtime = fileStat.mtimeMs;

    // 增量模式：跳过未变更文件
    if (incremental && index.files[file]?.mtime === mtime) {
      skipped++;
      continue;
    }

    const content = await readFile(file, 'utf-8');
    const ext = extname(file);

    if (ext === '.md') {
      const blocks = extractMermaidBlocks(content);
      if (blocks.length > 0) {
        const diagrams = blocks.map(b => {
          const info = parseMermaidDiagram(b.code);
          info.line = b.line;
          return info;
        });
        index.files[file] = { mtime, type: 'mermaid', diagrams };
        processed++;
      }
    } else if (ext === '.canvas') {
      try {
        const { nodes, edges } = parseCanvas(content);
        index.files[file] = { mtime, type: 'canvas', nodes, edges };
        processed++;
      } catch (e) {
        console.error(`解析失败: ${file}`, e);
      }
    }
  }

  console.log(`处理完成: ${processed} 个文件, 跳过: ${skipped} 个未变更`);
  return index;
}

// ==================== 查询函数 ====================

export function findNodeLocation(index: IndexData, nodeId: string): Array<{ file: string; line?: number }> {
  const results: Array<{ file: string; line?: number }> = [];

  for (const [file, data] of Object.entries(index.files)) {
    if (data.type === 'canvas' && data.nodes?.includes(nodeId)) {
      results.push({ file });
    }
    if (data.type === 'mermaid' && data.diagrams) {
      for (const d of data.diagrams) {
        if (d.participants?.includes(nodeId) || d.nodes?.includes(nodeId)) {
          results.push({ file, line: d.line });
        }
      }
    }
  }

  return results;
}

// ==================== CLI ====================

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes('--help')) {
    console.log(`
用法: bun index.ts <目录> [选项]

选项:
  --incremental    增量模式，仅处理变更文件
  --output <file>  输出文件路径 (默认: ./diagram-index.json)
  --verbose        详细输出
  --help           显示帮助
`);
    process.exit(0);
  }

  const dir = args[0];
  const incremental = args.includes('--incremental');
  const outputIdx = args.indexOf('--output');
  const output = outputIdx !== -1 ? args[outputIdx + 1] : './diagram-index.json';

  // 加载现有索引
  let existingIndex: IndexData | undefined;
  if (incremental) {
    try {
      const content = await readFile(output, 'utf-8');
      existingIndex = JSON.parse(content);
    } catch {
      // 文件不存在，从头构建
    }
  }

  const index = await buildIndex(dir, existingIndex, incremental);
  await writeFile(output, JSON.stringify(index, null, 2));
  console.log(`索引已保存: ${output}`);
}

main().catch(console.error);
