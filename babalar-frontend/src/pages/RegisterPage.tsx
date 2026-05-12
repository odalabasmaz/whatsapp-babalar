import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api/client";
import { useThemeStore } from "../store/theme";

export default function RegisterPage() {
  const [form, setForm] = useState({ email: "", username: "", password: "", invite_code: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState(false);
  const { theme, toggle } = useThemeStore();
  const navigate = useNavigate();

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/register", form);
      setRegistered(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Kayıt başarısız");
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
          <div className="text-5xl mb-3">👨‍👦</div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Babalar</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Münih Türk Topluluğu</p>
        </div>

        {registered ? (
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-800 p-6 text-center space-y-4">
            <div className="text-4xl">🎉</div>
            <div>
              <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">Hoş geldin, {form.username}!</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Hesabın başarıyla oluşturuldu.</p>
            </div>
            <div className="bg-green-50 dark:bg-green-900/20 rounded-xl p-4 text-left space-y-2">
              <p className="text-xs font-semibold text-green-700 dark:text-green-400 uppercase tracking-wide">Nasıl çalışır?</p>
              <ul className="text-sm text-gray-600 dark:text-gray-300 space-y-1.5">
                <li>💬 Münihli Babalar WhatsApp topluluğunun gerçek mesajlarından yanıt üretilir</li>
                <li>🔍 Her gün {5} soruya kadar sorabilirsin</li>
                <li>🇹🇷 Türkçe yaz, Türkçe cevap al</li>
                <li>📍 Münih'teki günlük yaşamla ilgili her şeyi sorabilirsin</li>
              </ul>
            </div>
            <button
              onClick={() => navigate("/login")}
              className="w-full bg-green-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-green-700 transition-colors"
            >
              Giriş Yap →
            </button>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-800 p-6">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-1">Kayıt Ol</h2>
            <p className="text-xs text-gray-400 dark:text-gray-500 mb-5">Kayıt için davet kodu gereklidir</p>

            <form onSubmit={handleSubmit} className="space-y-3">
              <input type="email" placeholder="Email" value={form.email} onChange={set("email")}
                className="w-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-400 dark:placeholder-gray-500"
                required autoComplete="email" />
              <input type="text" placeholder="Kullanıcı adı" value={form.username} onChange={set("username")}
                className="w-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-400 dark:placeholder-gray-500"
                required autoComplete="username" />
              <input type="password" placeholder="Şifre" value={form.password} onChange={set("password")}
                className="w-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-400 dark:placeholder-gray-500"
                required autoComplete="new-password" />

              <div className="pt-1">
                <div className="flex items-center gap-2 border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 rounded-xl px-4 py-2.5 focus-within:ring-2 focus-within:ring-green-500">
                  <span className="text-lg">🎟️</span>
                  <input type="text" placeholder="Davet kodu" value={form.invite_code} onChange={set("invite_code")}
                    className="flex-1 bg-transparent text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none"
                    required />
                </div>
                <p className="text-xs text-gray-400 mt-1 px-1">Topluluğa katılmak için davet kodu zorunludur</p>
              </div>

              {error && (
                <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
              )}
              <button type="submit" disabled={loading}
                className="w-full bg-green-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors mt-1">
                {loading ? "Kaydediliyor..." : "Kayıt Ol"}
              </button>
            </form>
            <p className="text-center text-sm mt-4 text-gray-500 dark:text-gray-400">
              Zaten hesabın var mı?{" "}
              <Link to="/login" className="text-green-600 hover:underline font-medium">Giriş Yap</Link>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
