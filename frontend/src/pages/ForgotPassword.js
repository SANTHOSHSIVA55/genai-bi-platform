import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import AuthLayout from '../components/AuthLayout';
import { forgotPassword } from '../api/api';
import { Loader2, Mail, MailCheck, AlertCircle } from 'lucide-react';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (sent) {
    return (
      <AuthLayout
        title="Check your inbox"
        subtitle="We&apos;ve sent you instructions to reset your password"
        footer={
          <>
            Remembered your password?{' '}
            <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
              Sign in
            </Link>
          </>
        }
      >
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <div className="w-14 h-14 rounded-apple bg-apple-green/10 border border-apple-green/20 flex items-center justify-center">
            <MailCheck className="w-7 h-7 text-apple-green" />
          </div>
          <p className="text-dark-300 text-sm leading-relaxed">
            If an account exists for <span className="text-dark-100 font-medium">{email}</span>, a
            password reset link is on its way. The link expires shortly, so check your inbox soon.
          </p>
          <Link to="/login" className="btn-secondary text-sm">
            Back to Sign In
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email and we&apos;ll send you a reset link"
      footer={
        <>
          Remembered your password?{' '}
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
          <label htmlFor="fp-email" className="block text-sm font-medium text-dark-300 mb-1.5">
            Email
          </label>
          <div className="relative">
            <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
            <input
              id="fp-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="input-field pl-10"
              required
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={submitting || !email.trim()}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
          {submitting ? 'Sending...' : 'Send Reset Link'}
        </button>
      </form>
    </AuthLayout>
  );
};

export default ForgotPassword;
