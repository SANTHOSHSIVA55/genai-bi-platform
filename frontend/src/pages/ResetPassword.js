import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthLayout from '../components/AuthLayout';
import { resetPassword } from '../api/api';
import { Loader2, KeyRound, AlertCircle, CheckCircle2 } from 'lucide-react';

const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/\d/.test(password)) {
      setError('Password must be at least 8 characters and include uppercase, lowercase and a number.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Reset failed. The link may be invalid or expired. Please request a new one.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <AuthLayout title="Invalid link" subtitle="This password reset link is missing its token">
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <div className="w-14 h-14 rounded-apple bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <AlertCircle className="w-7 h-7 text-red-400" />
          </div>
          <p className="text-dark-300 text-sm">
            Please use the link from your email to reset your password.
          </p>
          <Link to="/forgot-password" className="btn-secondary text-sm">
            Request a New Link
          </Link>
        </div>
      </AuthLayout>
    );
  }

  if (done) {
    return (
      <AuthLayout
        title="Password updated"
        subtitle="You can now sign in with your new password"
        footer={
          <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
            Go to Sign In
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <div className="w-14 h-14 rounded-apple bg-apple-green/10 border border-apple-green/20 flex items-center justify-center">
            <CheckCircle2 className="w-7 h-7 text-apple-green" />
          </div>
          <Link to="/login" className="btn-primary text-sm w-full text-center">
            Sign In Now
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="Your password must meet the security requirements">
      {error && (
        <div className="flex items-start gap-2.5 p-3 mb-4 rounded-apple bg-red-500/8 border border-red-500/15 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p>{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="np-password" className="block text-sm font-medium text-dark-300 mb-1.5">
            New password
          </label>
          <div className="relative">
            <KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
            <input
              id="np-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="input-field pl-10"
              required
            />
          </div>
        </div>

        <div>
          <label htmlFor="np-confirm" className="block text-sm font-medium text-dark-300 mb-1.5">
            Confirm new password
          </label>
          <input
            id="np-confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat your new password"
            className="input-field"
            required
          />
        </div>

        <button
          type="submit"
          disabled={submitting || !password || !confirm}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
          {submitting ? 'Updating...' : 'Update Password'}
        </button>
      </form>
    </AuthLayout>
  );
};

export default ResetPassword;
