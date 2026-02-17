/**
 * Step 3 (continued): Read competitor_analysis.json and generate positioning_summary.md.
 * Run: npx ts-node analyze_positioning.ts
 */

import * as fs from 'fs';
import * as path from 'path';

const ANALYSIS_PATH = path.join(__dirname, '..', 'competitor_analysis.json');
const OUT_PATH = path.join(__dirname, '..', 'positioning_summary.md');

interface CrawlResult {
  url: string;
  name: string;
  title: string | null;
  metaDescription: string | null;
  h1: string | null;
  h2s: string[];
  mainSnippet: string | null;
  wordCount: number;
  error?: string;
  crawledAt: string;
}

function escapeMd(s: string | null): string {
  if (s == null) return '—';
  return s.replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function main() {
  if (!fs.existsSync(ANALYSIS_PATH)) {
    console.log('Run crawl_competitors.ts first to generate competitor_analysis.json');
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(ANALYSIS_PATH, 'utf-8'));
  const results: CrawlResult[] = data.results || [];

  const lines: string[] = [
    '# Ceremonial Cacao USA — Competitor Positioning Summary',
    '',
    'Generated from crawler output. Use this to inform `seo_keyword_strategy.md`.',
    '',
    '## By competitor',
    '',
  ];

  for (const r of results) {
    lines.push(`### ${escapeMd(r.name)}`);
    lines.push('');
    lines.push(`| Field | Value |`);
    lines.push(`|-------|-------|`);
    lines.push(`| URL | ${r.url} |`);
    lines.push(`| Title | ${escapeMd(r.title)} |`);
    lines.push(`| Meta description | ${escapeMd(r.metaDescription)} |`);
    lines.push(`| H1 | ${escapeMd(r.h1)} |`);
    lines.push(`| H2s (sample) | ${(r.h2s || []).slice(0, 5).join('; ') || '—'} |`);
    if (r.mainSnippet) {
      lines.push(`| Main snippet | ${escapeMd(r.mainSnippet.slice(0, 300))}… |`);
    }
    if (r.error) lines.push(`| Error | ${r.error} |`);
    lines.push('');
  }

  lines.push('## Positioning dimensions to review');
  lines.push('');
  lines.push('- **Quality / ritual** vs convenience');
  lines.push('- **Origin**: single-origin vs blend');
  lines.push('- **Certifications**: organic, fair trade, etc.');
  lines.push('- **Community / ceremony** vs retail-only');
  lines.push('- **Price tier** and messaging');
  lines.push('');
  lines.push('*Edit this file and then draft `seo_keyword_strategy.md` (match + differentiate).*');

  fs.writeFileSync(OUT_PATH, lines.join('\n'), 'utf-8');
  console.log(`Wrote ${OUT_PATH}`);
}

main();
