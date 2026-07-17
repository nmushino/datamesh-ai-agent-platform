import { useState } from 'react';
import { useEntity } from '@backstage/plugin-catalog-react';
import { useApi, configApiRef } from '@backstage/core-plugin-api';
import { sendChatMessage, approveTask, ChatResponse } from '../../api';

const SITES = [
  { value: 'Aサイト', label: 'Aサイト (asite)' },
  { value: 'Bサイト', label: 'Bサイト (bsite)' },
  { value: 'Cサイト', label: 'Cサイト (csite)' },
];

type Phase = 'idle' | 'sending' | 'awaiting-approval' | 'approving' | 'done' | 'error';

function buildRequestMessage(
  topicName: string,
  site: string,
  repoSlug: string | undefined,
  comment: string,
): string {
  const lines = [
    'Developer Hub からのトピック作成依頼です。',
    `トピック名: ${topicName}`,
    `対象サイト: ${site}`,
  ];
  if (repoSlug) {
    lines.push(`対象リポジトリ: ${repoSlug}`);
  }
  lines.push(`追加コメント: ${comment.trim() || '(なし)'}`);
  lines.push(
    'このトピックが対象サイトの実ブローカーに既に存在する場合は何もせず、' +
      '存在しない場合のみ、追加コメントおよび対象リポジトリのソースコード/README' +
      'から説明文を組み立てた上で新規作成してください。',
  );
  return lines.join('\n');
}

export const TopicRequestContent = () => {
  const { entity } = useEntity();
  const config = useApi(configApiRef);
  const baseUrl =
    config.getOptionalString('aiAgent.baseUrl') ??
    config.getOptionalString('kafkaTopicRequest.apiBaseUrl') ??
    '';
  const repoSlug = entity.metadata.annotations?.['github.com/project-slug'];

  const [topicName, setTopicName] = useState('');
  const [site, setSite] = useState(SITES[0].value);
  const [comment, setComment] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [status, setStatus] = useState('');
  const [reply, setReply] = useState('');
  const [error, setError] = useState('');
  const [threadId, setThreadId] = useState('');

  const resetResult = () => {
    setPhase('idle');
    setStatus('');
    setReply('');
    setError('');
    setThreadId('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topicName.trim()) {
      setError('トピック名を入力してください。');
      setPhase('error');
      return;
    }
    if (!baseUrl) {
      setError(
        'AI Agent の接続先 (app-config.yaml の aiAgent.baseUrl) が設定されていません。',
      );
      setPhase('error');
      return;
    }

    setPhase('sending');
    setStatus('');
    setReply('');
    setError('');
    const newThreadId = crypto.randomUUID();
    setThreadId(newThreadId);

    try {
      const message = buildRequestMessage(topicName.trim(), site, repoSlug, comment);
      const res: ChatResponse = await sendChatMessage(
        baseUrl,
        message,
        newThreadId,
        s => setStatus(s),
      );
      setReply(res.reply);
      setPhase(res.requires_approval ? 'awaiting-approval' : 'done');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase('error');
    }
  };

  const handleApprove = async () => {
    if (!baseUrl || !threadId) return;
    setPhase('approving');
    setError('');
    try {
      const res = await approveTask(baseUrl, threadId);
      setReply(res.reply ?? res.status);
      setPhase('done');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase('error');
    }
  };

  return (
    <div style={{ padding: '24px', fontFamily: 'sans-serif', maxWidth: '640px' }}>
      <h2 style={{ marginBottom: '8px' }}>Kafka トピック作成依頼</h2>
      <p style={{ color: '#555', fontSize: '13px', marginBottom: '24px' }}>
        指定したトピック名が対象サイトにまだ存在しない場合のみ、AI Agent が
        追加コメントとこのアプリのソースコード/README から説明文を組み立てて
        新規作成します。既に存在する場合は何も変更されません。
      </p>

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '4px' }}>
            トピック名 *
          </label>
          <input
            type="text"
            value={topicName}
            onChange={e => setTopicName(e.target.value)}
            placeholder="例: order-events"
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
            disabled={phase === 'sending' || phase === 'approving'}
          />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '4px' }}>
            対象サイト *
          </label>
          <select
            value={site}
            onChange={e => setSite(e.target.value)}
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
            disabled={phase === 'sending' || phase === 'approving'}
          >
            {SITES.map(s => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '4px' }}>
            追加コメント(任意)
          </label>
          <textarea
            value={comment}
            onChange={e => setComment(e.target.value)}
            placeholder="このトピックの用途や流すデータについて補足があれば入力してください"
            rows={4}
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
            disabled={phase === 'sending' || phase === 'approving'}
          />
        </div>

        {repoSlug && (
          <p style={{ color: '#888', fontSize: '12px', marginBottom: '16px' }}>
            対象リポジトリ: {repoSlug}(このカタログエンティティの
            github.com/project-slug アノテーションから取得)
          </p>
        )}

        <button
          type="submit"
          disabled={phase === 'sending' || phase === 'approving'}
          style={{
            padding: '10px 24px',
            background: '#1976d2',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            fontWeight: 'bold',
            fontSize: '14px',
            cursor: phase === 'sending' ? 'not-allowed' : 'pointer',
          }}
        >
          {phase === 'sending' ? '送信中...' : 'AI Agent に依頼する'}
        </button>
      </form>

      {status && phase === 'sending' && (
        <p style={{ marginTop: '16px', color: '#1976d2' }}>{status}</p>
      )}

      {reply && (
        <div
          style={{
            marginTop: '24px',
            padding: '16px',
            background: '#f5f5f5',
            borderRadius: '8px',
            whiteSpace: 'pre-wrap',
          }}
        >
          {reply}
        </div>
      )}

      {phase === 'awaiting-approval' && (
        <button
          onClick={handleApprove}
          style={{
            marginTop: '16px',
            padding: '10px 24px',
            background: '#2e7d32',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            fontWeight: 'bold',
            fontSize: '14px',
            cursor: 'pointer',
          }}
        >
          承認してトピックを作成する
        </button>
      )}

      {phase === 'done' && (
        <div style={{ marginTop: '16px' }}>
          <button
            onClick={resetResult}
            style={{
              padding: '8px 16px',
              background: '#eee',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            別のトピックを依頼する
          </button>
        </div>
      )}

      {error && (
        <p style={{ marginTop: '16px', color: '#c62828' }}>エラー: {error}</p>
      )}
    </div>
  );
};
