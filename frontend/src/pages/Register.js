import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AuthLayout from '../components/AuthLayout';
import { Loader2, UserPlus, AlertCircle, CheckCircle2 } from 'lucide-react';
import toast from 'react-hot-toast';

const PASSWORD_RULES = [
  { test: (p) => p.length >= 8, label: 'At least 8 characters' },
  { test: (p) => /[a-z]/.test(p) && /[A-Z]/.test(p), label: 'Uppercase and lowercase letters' },
  { test: (p) => /\d/.test(p), label: 'At least one number' },
];

const Register = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!/^[a-zA-Z0-9_.-]{3,50}$/.test(username.trim())) {
      setError('Username may only contain letters, numbers, dots, dashes and underscores (3-50 characters).');
      return;
    }
    if (!PASSWORD_RULES.every((r) => r.test(password))) {
      setError('Password must be at least 8 characters and include uppercase, lowercase and a number.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      const user = await register({ email: email.trim(), username: username.trim(), password });
      toast.success(`Account created. Welcome, ${user.username}!`);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d) => d.msg).join(' '));
      } else {
        setError(typeof detail === 'string' ? detail : 'Registration failed. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start asking your data questions in minutes"
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
            Sign in
          </Link>
        </>
      }
    >
      {error && (
        <div className="flex items-start gap-2.5 p-3 mb-4 rounded-apple bg-red-500/8 border border-red-500/15 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p>{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="username" className="block text-sm font-medium text-dark-300 mb-1.5">
            Username
          </label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="analyst_jane"
            className="input-field"
            required
          />
        </div>

        <div>
          <label htmlFor="reg-email" className="block text-sm font-medium text-dark-300 mb-1.5">
            Email
          </label>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="input-field"
            required
          />
        </div>

        <div>
          <label htmlFor="reg-password" className="block text-sm font-medium text-dark-300 mb-1.5">
            Password
          </label>
          <input
            id="reg-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Create a strong password"
            className="input-field"
            required
          />
          <ul className="mt-2 space-y-1">
            {PASSWORD_RULES.map((rule) => {
              const ok = rule.test(password);
              return (
                <li
                  key={rule.label}
                  className={`flex items-center gap-1.5 text-xs ${
                    ok ? 'text-apple-green' : 'text-dark-500'
                  }`}
                >
                  <CheckCircle2 className="w-3 h-3" />
                  {rule.label}
                </li>
              );
            })}
          </ul>
        </div>

        <div>
          <label htmlFor="reg-confirm" className="block text-sm font-medium text-dark-300 mb-1.5">
            Confirm password
          </label>
          <input
            id="reg-confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat your password"
            className="input-field"
            required
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {submitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <UserPlus className="w-4 h-4" />
          )}
          {submitting ? 'Creating account...' : 'Create Account'}
        </button>
      </form>
    </AuthLayout>
  );
};

export default Register;
