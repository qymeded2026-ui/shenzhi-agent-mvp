import { useState, type FormEvent, type ReactNode } from "react";
import { Eye, EyeOff, Lock, Phone, ShieldCheck, User, X } from "lucide-react";
import type { AppUser } from "../App";
import { BrandLogo } from "./BrandLogo";

type LoginTab = "password" | "sms";

interface LoginPageProps {
  onLogin: (user: AppUser) => void;
  onClose?: () => void;
}

export function LoginPage({ onLogin, onClose }: LoginPageProps) {
  const [tab, setTab] = useState<LoginTab>("password");
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [countdown, setCountdown] = useState(0);

  const sendCode = () => {
    if (!/^1\d{10}$/.test(phone)) return;
    setCountdown(60);
    const timer = window.setInterval(() => {
      setCountdown((current) => {
        if (current <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return current - 1;
      });
    }, 1000);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = tab === "password" ? account.trim() || "超级管理员" : `用户${phone.slice(-4) || "0000"}`;

    onLogin({
      name,
      email: tab === "password" ? `${account.trim() || "admin"}@shenzhi.ai` : undefined,
      role: "管理员",
    });
  };

  return (
    <div data-testid="login-page" className="fixed inset-0 z-[100] flex bg-white">
      <div className="relative hidden flex-1 items-center justify-center overflow-hidden bg-gradient-to-br from-[#0f2027] via-[#134e4a] to-[#0d9488] text-white md:flex">
        <div className="absolute -left-32 -top-32 h-96 w-96 rounded-full bg-teal-400/20 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-[28rem] w-[28rem] rounded-full bg-emerald-300/10 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{ backgroundImage: "radial-gradient(white 1px, transparent 1px)", backgroundSize: "24px 24px" }}
        />

        <div className="relative scale-150">
          <BrandLogo />
        </div>
      </div>

      <div className="relative flex flex-1 items-center justify-center px-6 py-10">
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="absolute right-5 top-5 flex h-9 w-9 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        )}

        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h2 className="mb-2 text-2xl font-medium text-gray-800">欢迎回来</h2>
            <p className="text-sm text-gray-500">登录后开启你的问诊训练之旅</p>
          </div>

          <div className="mb-6 flex gap-6 border-b border-gray-200">
            {[
              { key: "password" as const, label: "账号密码" },
              { key: "sms" as const, label: "短信验证码" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                className={`relative pb-3 text-sm transition-colors ${
                  tab === item.key ? "text-teal-600" : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {item.label}
                {tab === item.key && <span className="absolute -bottom-px left-0 right-0 h-0.5 rounded-full bg-teal-500" />}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            {tab === "password" ? (
              <>
                <FieldWrap icon={<User size={15} className="text-gray-400" />}>
                  <input
                    type="text"
                    placeholder="账号 / 邮箱"
                    value={account}
                    onChange={(event) => setAccount(event.target.value)}
                    className="flex-1 bg-transparent text-sm text-gray-700 outline-none placeholder:text-gray-300"
                  />
                </FieldWrap>
                <FieldWrap icon={<Lock size={15} className="text-gray-400" />}>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="密码"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="flex-1 bg-transparent text-sm text-gray-700 outline-none placeholder:text-gray-300"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((visible) => !visible)}
                    className="text-gray-400 transition-colors hover:text-gray-600"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </FieldWrap>
              </>
            ) : (
              <>
                <FieldWrap icon={<Phone size={15} className="text-gray-400" />}>
                  <input
                    type="tel"
                    placeholder="手机号"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value.replace(/\D/g, "").slice(0, 11))}
                    className="flex-1 bg-transparent text-sm text-gray-700 outline-none placeholder:text-gray-300"
                  />
                </FieldWrap>
                <FieldWrap icon={<ShieldCheck size={15} className="text-gray-400" />}>
                  <input
                    type="text"
                    placeholder="6 位验证码"
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    className="flex-1 bg-transparent text-sm text-gray-700 outline-none placeholder:text-gray-300"
                  />
                  <button
                    type="button"
                    onClick={sendCode}
                    disabled={countdown > 0 || !/^1\d{10}$/.test(phone)}
                    className="whitespace-nowrap text-sm text-teal-600 transition-colors hover:text-teal-700 disabled:cursor-not-allowed disabled:text-gray-300"
                  >
                    {countdown > 0 ? `${countdown}s 后重发` : "获取验证码"}
                  </button>
                </FieldWrap>
              </>
            )}

            <div className="flex items-center justify-between pt-1 text-sm">
              <label className="flex cursor-pointer select-none items-center gap-2 text-gray-500">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                  className="h-3.5 w-3.5 accent-teal-500"
                />
                7 天内自动登录
              </label>
              <button type="button" className="text-teal-600 transition-colors hover:text-teal-700">
                忘记密码?
              </button>
            </div>

            <button
              type="submit"
              data-testid="login-submit"
              className="w-full rounded-lg bg-gradient-to-br from-teal-500 to-teal-600 py-3 text-sm text-white shadow-sm shadow-teal-500/20 transition-all hover:from-teal-600 hover:to-teal-700"
            >
              登 录
            </button>

            <div className="flex items-center gap-3 py-2">
              <div className="h-px flex-1 bg-gray-200" />
              <span className="text-xs text-gray-400">其他登录方式</span>
              <div className="h-px flex-1 bg-gray-200" />
            </div>

            <div className="flex justify-center gap-4">
              {[
                { label: "微信", color: "bg-emerald-500" },
                { label: "企业微信", color: "bg-sky-500" },
                { label: "扫码", color: "bg-gray-700" },
              ].map((provider) => (
                <button
                  key={provider.label}
                  type="button"
                  className="flex h-10 w-10 items-center justify-center rounded-full border border-gray-200 text-xs text-gray-500 transition-colors hover:border-teal-300 hover:bg-teal-50"
                  title={provider.label}
                >
                  <span className={`h-2 w-2 rounded-full ${provider.color}`} />
                </button>
              ))}
            </div>

            <p className="pt-2 text-center text-sm text-gray-500">
              还没有账号?
              <button type="button" className="ml-1 text-teal-600 transition-colors hover:text-teal-700">
                申请试用
              </button>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

function FieldWrap({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-gray-200 px-3.5 py-3 transition-all focus-within:border-teal-400 focus-within:ring-2 focus-within:ring-teal-100">
      {icon}
      {children}
    </div>
  );
}
