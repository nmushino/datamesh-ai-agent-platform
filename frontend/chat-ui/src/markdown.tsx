import type { ReactNode } from "react";

// 軽量な Markdown レンダラー。外部ライブラリを追加せず、エージェントの応答で
// 実際に使われる範囲 (見出し / GFM テーブル / 太字 / 段落) だけをサポートする。

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
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

export function renderMarkdown(content: string): ReactNode[] {
  const lines = content.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let blockKey = 0;

  while (i < lines.length) {
    const line = lines[i];

    // GFM テーブル: ヘッダ行の次が区切り行(---)であるものだけを対象にする
    if (
      line.includes("|") &&
      i + 1 < lines.length &&
      isTableSeparatorRow(lines[i + 1])
    ) {
      const headerCells = parseTableRow(line);
      const rows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].includes("|") && lines[j].trim() !== "") {
        rows.push(parseTableRow(lines[j]));
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
