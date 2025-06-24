import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/tauri';
import { FaGoogle, FaMicrosoft, FaEnvelope } from 'react-icons/fa';

interface LoginScreenProps {
  onLogin: () => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const handleOAuthLogin = async (provider: 'google' | 'microsoft') => {
    setIsLoading(true);
    try {
      await invoke('login', { provider });
      onLogin();
    } catch (error) {
      console.error('Login failed:', error);
      alert('Login failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await invoke('login_email', { email });
      setEmailSent(true);
    } catch (error) {
      console.error('Email login failed:', error);
      alert('Failed to send login email. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="bg-white p-8 rounded-2xl shadow-xl w-full max-w-md">
        <div className="text-center mb-8">
          <img src="/logo.png" alt="Context Hub" className="w-20 h-20 mx-auto mb-4" />
          <h1 className="text-3xl font-bold text-gray-800">Welcome to Context Hub</h1>
          <p className="text-gray-600 mt-2">Your AI-powered filesystem in the cloud</p>
        </div>

        {!emailSent ? (
          <>
            <div className="space-y-4">
              <button
                onClick={() => handleOAuthLogin('google')}
                disabled={isLoading}
                className="w-full flex items-center justify-center space-x-3 bg-white border border-gray-300 rounded-lg px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                <FaGoogle className="text-red-500 text-xl" />
                <span className="text-gray-700 font-medium">Continue with Google</span>
              </button>

              <button
                onClick={() => handleOAuthLogin('microsoft')}
                disabled={isLoading}
                className="w-full flex items-center justify-center space-x-3 bg-white border border-gray-300 rounded-lg px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                <FaMicrosoft className="text-blue-600 text-xl" />
                <span className="text-gray-700 font-medium">Continue with Microsoft</span>
              </button>

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white text-gray-500">Or</span>
                </div>
              </div>

              <form onSubmit={handleEmailLogin} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                    Email address
                  </label>
                  <div className="relative">
                    <FaEnvelope className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                    <input
                      type="email"
                      id="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder="you@example.com"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-blue-600 text-white rounded-lg px-4 py-3 font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {isLoading ? 'Sending...' : 'Send Magic Link'}
                </button>
              </form>
            </div>

            <p className="text-center text-sm text-gray-600 mt-6">
              By continuing, you agree to our{' '}
              <a href="#" className="text-blue-600 hover:underline">Terms of Service</a>
              {' and '}
              <a href="#" className="text-blue-600 hover:underline">Privacy Policy</a>
            </p>
          </>
        ) : (
          <div className="text-center py-8">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <FaEnvelope className="text-green-600 text-2xl" />
            </div>
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Check your email!</h2>
            <p className="text-gray-600">
              We've sent a magic link to <strong>{email}</strong>
            </p>
            <p className="text-sm text-gray-500 mt-4">
              Click the link in the email to sign in. You can close this window.
            </p>
            <button
              onClick={() => setEmailSent(false)}
              className="mt-6 text-blue-600 hover:underline text-sm"
            >
              Use a different email
            </button>
          </div>
        )}
      </div>
    </div>
  );
};