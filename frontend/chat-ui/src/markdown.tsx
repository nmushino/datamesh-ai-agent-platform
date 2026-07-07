import type { ReactNode } from "react";

// 軽量な Markdown レンダラー。外部ライブラリを追加せず、エージェントの応答で
// 実際に使われる範囲 (見出し / GFM テーブル / 太字 / リンク / 段落) だけをサポートする。

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  // 根拠となるデータソースへのリンクを表示するため [表示文字](URL) 記法にも対応する。
  const parts = text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)]+\))/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    const linkMatch = /^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/.exec(part);
    if (linkMatch) {
      return (
        <a key={`${keyPrefix}-${i}`} href={linkMatch[2]} target="_blank" rel="noreferrer">
          {linkMatch[1]}
        </a>
      );
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

function isTableSeparatorRow(line: string): boolean {
  return /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(line.trim());
}

function parseTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

// AIモデルは「名前列を [名前](URL) のMarkdownリンクにする」という指示を
// 何度強化しても毎回プレーンテキストに戻してしまう(検証済み)ため、
// FQN列の値からフロントエンド側で機械的にリンクを組み立てる。
function openMetadataBaseUrl(): string {
  const configured = window.__APP_CONFIG__?.openMetadataUrl ?? "";
  // 設定値は "http://host/my-data" のようにページパス付きのことがあるため、
  // オリジン(スキーム+ホスト)部分だけを取り出す。
  try {
    return new URL(configured).origin;
  } catch {
    return "";
  }
}

function entityTypeFromHeading(headingText: string): string {
  if (headingText.includes("トピック")) return "topic";
  if (headingText.includes("データプロダクト")) return "dataProduct";
  if (headingText.includes("パイプライン")) return "pipeline";
  return "table";
}

function linkifyFqnCell(fqn: string, entityType: string): string {
  const base = openMetadataBaseUrl();
  if (!base || !fqn || fqn.startsWith("[") || fqn === "-" || fqn === "...") return fqn;
  return `[${fqn}](${base}/${entityType}/${encodeURIComponent(fqn)})`;
}

export function renderMarkdown(content: string): ReactNode[] {
  const lines = content.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let blockKey = 0;
  let currentEntityType = "table";

  while (i < lines.length) {
    const line = lines[i];

    // GFM テーブル: ヘッダ行の次が区切り行(---)であるものだけを対象にする
    if (
      line.includes("|") &&
      i + 1 < lines.length &&
      isTableSeparatorRow(lines[i + 1])
    ) {
      const headerCells = parseTableRow(line);
      const fqnColumnIndex = headerCells.findIndex((h) => h.toUpperCase() === "FQN");
      const rows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].includes("|") && lines[j].trim() !== "") {
        const row = parseTableRow(lines[j]);
        if (fqnColumnIndex >= 0 && row[fqnColumnIndex]) {
          row[fqnColumnIndex] = linkifyFqnCell(row[fqnColumnIndex], currentEntityType);
        }
        rows.push(row);
        j++;
      }
      const key = `table-${blockKey++}`;
      blocks.push(
        <div className="chat-markdown-table-wrapper" key={key}>
          <table className="chat-markdown-table">
            <thead>
              <tr>
                {headerCells.map((c, ci) => (
                  <th key={`${key}-h${ci}`}>{renderInline(c, `${key}-h${ci}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={`${key}-r${ri}`}>
                  {r.map((c, ci) => (
                    <td key={`${key}-r${ri}-c${ci}`}>{renderInline(c, `${key}-r${ri}-c${ci}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = j;
      continue;
    }

    // 見出し (### 見出し)
    const headingMatch = /^(#{1,4})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const key = `heading-${blockKey++}`;
      const HeadingTag = (`h${Math.min(level + 2, 6)}`) as keyof JSX.IntrinsicElements;
      currentEntityType = entityTypeFromHeading(headingMatch[2]);
      blocks.push(<HeadingTag key={key}>{renderInline(headingMatch[2], key)}</HeadingTag>);
      i++;
      continue;
    }

    // 空行はスキップ、それ以外は段落として1行ずつ表示
    if (line.trim() === "") {
      i++;
      continue;
    }
    const key = `p-${blockKey++}`;
    blocks.push(<p key={key}>{renderInline(line, key)}</p>);
    i++;
  }

  return blocks;
}
