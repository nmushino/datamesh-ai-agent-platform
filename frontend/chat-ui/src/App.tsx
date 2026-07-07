import { useEffect, useState } from "react";
import { useAppAuth } from "./useAppAuth";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ChatBody } from "./components/ChatBody";
import { Footer } from "./components/Footer";
import { SettingsModal } from "./components/SettingsModal";
import { useThreads } from "./useThreads";
import { useScheduledTasks } from "./useScheduledTasks";
import { useNotifications } from "./useNotifications";
import { useAppSettings } from "./useAppSettings";
import { sendChatMessage, approveTask } from "./api";
import type { ChatSettings, ScheduledTask } from "./types";

const SIDEBAR_DEFAULT_WIDTH = 300;

export default function App() {
  const auth = useAppAuth();
  const {
    threads,
    activeThread,
    activeThreadId,
    setActiveThreadId,
    createThread,
    appendMessage,
    updateMessage,
    deleteThread,
  } = useThreads();
  const { tasks: scheduledTasks, deleteTask: deleteScheduledTask } = useScheduledTasks();
  const { notifications, unreadCount, markAllRead, addLocalNotification } =
    useNotifications();
  const { appSettings, updateAppSettings } = useAppSettings();
  const [sending, setSending] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [showQuickActions, setShowQuickActions] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chatSettings, setChatSettings] = useState<ChatSettings>({
    enableThinking: appSettings.defaultEnableThinking,
    maxTokensLevel: appSettings.defaultMaxTokensLevel,
  });

  // 未ログインなら自動でKeycloakのログイン画面へリダイレクトする
  useEffect(() => {
    if (
      !auth.isLoading &&
      !auth.isAuthenticated &&
      !auth.activeNavigator &&
      !auth.error
    ) {
      auth.signinRedirect();
    }
  }, [auth]);

  const handleSend = async (message: string) => {
    setShowQuickActions(false);
    const threadId = activeThreadId ?? createThread();
    appendMessage(threadId, {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
      createdAt: Date.now(),
    });
    setSending(true);
    setStatusText(null);
    try {
      const res = await sendChatMessage(
        message,
        threadId,
        auth.user?.access_token,
        setStatusText,
        chatSettings
      );
      appendMessage(threadId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.reply,
        createdAt: Date.now(),
        tokenUsage: res.token_usage,
        requiresApproval: res.requires_approval,
        approvalAction: res.approval_action,
        taskStatus: res.requires_approval ? "idle" : undefined,
      });
    } catch (e) {
      // ネットワーク断・タイムアウト時、ブラウザは "TypeError: Failed to fetch" を投げるが
      // ユーザーには技術的な文言でなく分かりやすいメッセージを表示し、
      // 原因の詳細は補足としてグレー文字で下に添える
      const isNetworkError = e instanceof TypeError;
      appendMessage(threadId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: isNetworkError ? "回答できませんでした" : "エラーが発生しました。",
        createdAt: Date.now(),
        errorReason: (e as Error).message,
      });
      addLocalNotification({
        status: "ERROR",
        message: isNetworkError
          ? "通信エラーによりチャットの応答を取得できませんでした。"
          : `チャットでエラーが発生しました: ${(e as Error).message}`,
        timestamp: new Date().toLocaleString("ja-JP"),
      });
    } finally {
      setSending(false);
      setStatusText(null);
    }
  };

  // タスクボタン: 承認が必要な長時間処理をバックグラウンドで実行し、
  // 完了したらチャットには結果メッセージを追加、通知ベルにも表示する。
  // ユーザーはボタンを押した後すぐ他の操作に戻れる(応答を待つ間ブロックしない)。
  const handleApprove = (threadId: string, messageId: string) => {
    updateMessage(threadId, messageId, { taskStatus: "running" });
    approveTask(threadId, auth.user?.access_token)
      .then((res) => {
        updateMessage(threadId, messageId, { taskStatus: "done" });
        appendMessage(threadId, {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.reply ?? "処理が完了しました。",
          createdAt: Date.now(),
        });
        addLocalNotification({
          status: "SUCCESS",
          message: res.reply ?? "タスクが完了しました。",
          timestamp: new Date().toLocaleString("ja-JP"),
        });
      })
      .catch((e) => {
        updateMessage(threadId, messageId, { taskStatus: "error" });
        addLocalNotification({
          status: "ERROR",
          message: `タスクの実行に失敗しました: ${(e as Error).message}`,
          timestamp: new Date().toLocaleString("ja-JP"),
        });
      });
  };

  // 定期チェック実行履歴の項目をクリックすると、専用スレッド「定期チェック実行履歴」に
  // 結果を追記する。スレッドが無ければ作成し、既にあれば再利用して同じスレッドの
  // 下に続けて記載していく(クリックのたびに新規会話は作らない)。
  const SCHEDULED_TASK_THREAD_TITLE = "定期チェック実行履歴";
  const handleSelectScheduledTask = (task: ScheduledTask) => {
    const existing = threads.find((t) => t.title === SCHEDULED_TASK_THREAD_TITLE);
    const threadId = existing ? existing.id : createThread(SCHEDULED_TASK_THREAD_TITLE);
    if (existing) {
      setActiveThreadId(existing.id);
    }
    setShowQuickActions(false);
    appendMessage(threadId, {
      id: crypto.randomUUID(),
      role: "assistant",
      content:
        `### 定期チェック実行結果\n\n` +
        `- **タスク**: ${task.task_name}\n` +
        `- **対象**: ${task.fqn}\n` +
        `- **ステータス**: ${task.status}\n` +
        `- **時刻**: ${new Date(task.timestamp).toLocaleString("ja-JP")}\n\n` +
        `${task.message}`,
      createdAt: Date.now(),
    });
  };

  if (auth.error) {
    return (
      <div className="auth-status">
        認証エラーが発生しました: {auth.error.message}
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return <div className="auth-status">ログイン画面にリダイレクトしています...</div>;
  }

  return (
    <div className="app-shell">
      <Header
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        notifications={notifications}
        unreadCount={unreadCount}
        markAllRead={markAllRead}
      />
      <div className="app-content">
        <Sidebar
          threads={threads}
          activeThreadId={activeThreadId}
          onSelect={(id) => {
            setShowQuickActions(false);
            setActiveThreadId(id);
          }}
          onCreate={() => {
            createThread();
            setShowQuickActions(true);
          }}
          onDelete={deleteThread}
          open={sidebarOpen}
          width={sidebarWidth}
          onResizeWidth={setSidebarWidth}
          scheduledTasks={scheduledTasks}
          onDeleteScheduledTask={deleteScheduledTask}
          onSelectScheduledTask={handleSelectScheduledTask}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <ChatBody
          thread={activeThread}
          sending={sending}
          statusText={statusText}
          showQuickActions={showQuickActions}
          onSend={handleSend}
          onApprove={(messageId) =>
            activeThreadId && handleApprove(activeThreadId, messageId)
          }
          chatSettings={chatSettings}
          onChatSettingsChange={setChatSettings}
          userMessageCollapseLines={appSettings.userMessageCollapseLines}
          assistantMessageCollapseLines={appSettings.assistantMessageCollapseLines}
        />
      </div>
      <Footer />
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        appSettings={appSettings}
        onChangeAppSettings={updateAppSettings}
      />
    </div>
  );
}
