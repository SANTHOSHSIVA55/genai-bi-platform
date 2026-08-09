import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthLayout from '../components/AuthLayout';
import { verifyEmail, resendVerification } from '../api/api';
import { Loader2, ShieldCheck, AlertCircle, MailCheck } from 'lucide-react';
import toast from 'react-hot-toast';

const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [status, setStatus] = useState(token ? 'verifying' : 'idle');
  const [error, setError] = useState(null);
  const [email, setEmail] = useState('');
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!token || status !== 'verifying') return;
    let cancelled = false;
    const run = async () => {
      try {
        await verifyEmail(token);
        if (!cancelled) setStatus('verified');
      } catch (err) {
        const detail = err.response?.data?.detail;
        if (!cancelled) {
          setStatus('failed');
          setError(typeof detail === 'string' ? detail : 'Verification failed.');
        }
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [token, status]);

  const handleResend = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setResending(true);
    try {
      await resendVerification(email.trim());
      toast.success('Verification email sent. Please check your inbox.');
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Could not resend the verification email.');
    } finally {
      setResending(false);
    }
  };

  if (status === 'verifying') {
    return (
      <AuthLayout title="Verifying your email" subtitle="Just a moment...">
        <div className="flex flex-col items-center gap-4 py-8">
          <Loader2 className="w-8 h-8 text-primary-400 animate-spin" />
          <p className="text-dark-400 text-sm">Confirming your email address.</p>
        </div>
      </AuthLayout>
    );
  }

  if (status === 'verified') {
    return (
      <AuthLayout
        title="Email verified"
        subtitle="Your account is ready to use"
        footer={
          <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
            Go to Sign In
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <div className="w-14 h-14 rounded-apple bg-apple-green/10 border border-apple-green/20 flex items-center justify-center">
            <ShieldCheck className="w-7 h-7 text-apple-green" />
          </div>
          <p className="text-dark-300 text-sm">
            Thanks for confirming your email. You can now fully access your workspace.
          </p>
          <Link to="/login" className="btn-primary text-sm w-full text-center">
            Sign In
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={token ? 'Verification failed' : 'Verify your email'}
      subtitle={token ? 'We couldn&apos;t verify this token' : 'Enter your email to receive a verification link'}
    >
      {error && (
        <div className="flex items-start gap-2.5 p-3 mb-4 rounded-apple bg-red-500/8 border border-red-500/15 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p>{error}</p>
        </div>
      )}

      <form onSubmit={handleResend} className="space-y-4">
        <div>
          <label htmlFor="ve-email" className="block text-sm font-medium text-dark-300 mb-1.5">
            Email
          </label>
          <input
            id="ve-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="input-field"
            required
          />
        </div>
        <button
          type="submit"
          disabled={resending || !email.trim()}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {resending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <MailCheck className="w-4 h-4" />
          )}
          {resending ? 'Sending...' : 'Resend Verification Email'}
        </button>
      </form>
    </AuthLayout>
  );
};

export default VerifyEmail;
