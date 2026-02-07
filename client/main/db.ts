import Database from 'better-sqlite3';
import * as path from 'path';
import { app } from 'electron';
import type { Job } from '../src/types/job';

let db: Database.Database;

type DbJobRow = Omit<Job, 'error'> & {
  error_json: string | null;
};

export function initDb(customPath?: string) {
  const dbPath = customPath || path.join(app.getPath('userData'), 'entrocut.db');
  db = new Database(dbPath);

  // 创建 jobs 表
  db.exec(`
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      state TEXT NOT NULL,
      phase TEXT,
      progress INTEGER DEFAULT 0,
      video_path TEXT NOT NULL,
      output_video TEXT,
      error_json TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    )
  `);

  console.log(`[DB] Database initialized at ${dbPath}`);
}

export function saveJob(job: Partial<Job> & { id: string }) {
  const existing = db.prepare('SELECT id FROM jobs WHERE id = ?').get(job.id);

  if (existing) {
    const sets: string[] = [];
    const values: unknown[] = [];

    if (job.state) { sets.push('state = ?'); values.push(job.state); }
    if (job.phase) { sets.push('phase = ?'); values.push(job.phase); }
    if (job.progress !== undefined) { sets.push('progress = ?'); values.push(job.progress); }
    if (job.output_video) { sets.push('output_video = ?'); values.push(job.output_video); }
    if (job.error) { sets.push('error_json = ?'); values.push(JSON.stringify(job.error)); }
    
    sets.push("updated_at = datetime('now')");
    values.push(job.id);

    db.prepare(`UPDATE jobs SET ${sets.join(', ')} WHERE id = ?`).run(...values);
  } else {
    db.prepare(`
      INSERT INTO jobs (id, state, phase, progress, video_path, output_video, error_json)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      job.id,
      job.state || 'IDLE',
      job.phase || null,
      job.progress || 0,
      job.video_path || '',
      job.output_video || null,
      job.error ? JSON.stringify(job.error) : null
    );
  }
}

export function getJob(id: string): Job | undefined {
  const row = db.prepare('SELECT * FROM jobs WHERE id = ?').get(id) as DbJobRow | undefined;
  if (!row) return undefined;

  return {
    ...row,
    error: row.error_json ? JSON.parse(row.error_json) : undefined
  };
}

export function getAllJobs(): Job[] {
  const rows = db.prepare('SELECT * FROM jobs ORDER BY created_at DESC').all() as DbJobRow[];
  return rows.map(row => ({
    ...row,
    error: row.error_json ? JSON.parse(row.error_json) : undefined
  }));
}
