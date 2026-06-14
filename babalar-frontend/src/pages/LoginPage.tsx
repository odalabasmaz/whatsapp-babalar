import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api/client";
import { useAuthStore } from "../store/auth";
import { useThemeStore } from "../store/theme";

export default function LoginPage() {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { setTokens, setUser } = useAuthStore();
  const { theme, toggle } = useThemeStore();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/auth/login", { identifier, password });
      setTokens(res.data.access_token, res.data.refresh_token);
      const me = await api.get("/auth/me");
      setUser(me.data);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center p-4">
      <button onClick={toggle} className="fixed top-4 right-4 p-2 rounded-lg text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors">
        {theme === "dark" ? "☀️" : "🌙"}
      </button>

      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <img src="/logo.jpg" alt="Babalar" className="w-24 h-24 rounded-full mx-auto mb-3 object-cover shadow-md" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Babalar</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Münih Türk Topluluğu</p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-800 p-6">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-5">Giriş Yap</h2>
          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="text"
              placeholder="Kullanıcı adı veya email"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="w-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-400 dark:placeholder-gray-500"
              required
              autoComplete="username"
            />
            <input
              type="password" placeholder="Şifre" value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-400 dark:placeholder-gray-500"
              required
              autoComplete="current-password"
            />
            {error && (
              <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
            )}
            <button
              type="submit" disabled={loading}
              className="w-full bg-green-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors mt-1"
            >
              {loading ? "Giriş yapılıyor..." : "Giriş Yap"}
            </button>
          </form>
          <p className="text-center text-sm mt-4 text-gray-500 dark:text-gray-400">
            Hesabın yok mu?{" "}
            <Link to="/register" className="text-green-600 hover:underline font-medium">Kayıt Ol</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
