import { AlertTriangle } from "lucide-react";
import type { MouseEventHandler, ReactNode } from "react";
import clsx from "clsx";

interface ErrorDisplayProps {
  message: string;
  onRetry?: MouseEventHandler<HTMLButtonElement>;
  details?: ReactNode;
  retryLabel?: string;
}

export function ErrorDisplay({
  message,
  onRetry,
  details,
  retryLabel = "Try Again",
}: ErrorDisplayProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-200px)] -mt-8 px-6">
      <div className="w-full max-w-lg rounded-[32px] border border-red-200 bg-white/80 backdrop-blur-xl shadow-xl p-8 text-center space-y-6">
        <div className="flex flex-col items-center space-y-4">
          <span className="inline-flex items-center justify-center h-16 w-16 rounded-2xl bg-red-50 text-red-500 ring-1 ring-red-100">
            <AlertTriangle className="h-8 w-8" />
          </span>
          <h2 className="text-2xl font-semibold text-gray-900">
            Something went wrong
          </h2>
        </div>

        <p className="text-base text-gray-700 leading-relaxed">{message}</p>

        {details && (
          <div className="rounded-2xl border border-gray-200 bg-gray-50/70 px-5 py-4 text-sm text-gray-600 text-left space-y-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Details
            </h3>
            <div className="text-gray-600">{details}</div>
          </div>
        )}

        <div className="flex items-center justify-center gap-3">
          <button
            onClick={onRetry}
            disabled={!onRetry}
            className={clsx(
              "px-6 py-3 rounded-xl text-white font-semibold transition-colors shadow-md",
              onRetry
                ? "bg-emerald-500 hover:bg-emerald-600"
                : "bg-gray-300 cursor-not-allowed"
            )}
          >
            {retryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

