import { useEffect, useState } from "react";
import { useAppAuth } from "./useAppAuth";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ChatBody } from "./components/ChatBody";
import { Footer } from "./components/Footer";
import { useThreads } from "./useThreads";
import { useScheduledTasks } from "./useScheduledTasks";
import { sendChatMessage } from "./api";

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
    deleteThread,
  } = useThreads();
  const { tasks: scheduledTasks } = useScheduledTasks();
  const [sending, setSending] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [showQuickActions, setShowQuickActions] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);

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
        setStatusText
      );
      appendMessage(threadId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.reply,
        createdAt: Date.now(),
        tokenUsage: res.token_usage,
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
    } finally {
      setSending(false);
      setStatusText(null);
    }
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
      <Header onToggleSidebar={() => setSidebarOpen((v) => !v)} />
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
        />
        <ChatBody
          thread={activeThread}
          sending={sending}
          statusText={statusText}
          showQuickActions={showQuickActions}
          onSend={handleSend}
        />
      </div>
      <Footer />
    </div>
  );
}
