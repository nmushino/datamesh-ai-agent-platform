import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ChatBody } from "./components/ChatBody";
import { useThreads } from "./useThreads";
import { sendChatMessage } from "./api";

export default function App() {
  const auth = useAuth();
  const {
    threads,
    activeThread,
    activeThreadId,
    setActiveThreadId,
    createThread,
    appendMessage,
    deleteThread,
  } = useThreads();
  const [sending, setSending] = useState(false);

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
    const threadId = activeThreadId ?? createThread();
    appendMessage(threadId, {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
      createdAt: Date.now(),
    });
    setSending(true);
    try {
      const res = await sendChatMessage(message, threadId, auth.user?.access_token);
      appendMessage(threadId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.reply,
        createdAt: Date.now(),
      });
    } catch (e) {
      appendMessage(threadId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `エラーが発生しました: ${(e as Error).message}`,
        createdAt: Date.now(),
      });
    } finally {
      setSending(false);
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
      <Header />
      <div className="app-content">
        <Sidebar
          threads={threads}
          activeThreadId={activeThreadId}
          onSelect={setActiveThreadId}
          onCreate={createThread}
          onDelete={deleteThread}
        />
        <ChatBody thread={activeThread} sending={sending} onSend={handleSend} />
      </div>
    </div>
  );
}
