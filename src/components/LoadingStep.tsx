import { Loader2, Check } from 'lucide-react';

interface LoadingStepProps {
  text: string;
  status: 'pending' | 'loading' | 'complete';
}

export function LoadingStep({ text, status }: LoadingStepProps) {
  // Don't render if pending
  if (status === 'pending') return null;

  return (
    <div className="flex items-center justify-between py-3">
      <span className={`${status === 'complete' ? 'text-gray-900' : 'text-gray-600'}`}>
        {text}
      </span>
      <div className="flex-shrink-0 ml-3">
        {status === 'loading' && (
          <Loader2 className="w-5 h-5 text-emerald-600 animate-spin" />
        )}
        {status === 'complete' && (
          <div className="w-5 h-5 rounded-sm bg-emerald-600 flex items-center justify-center">
            <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
          </div>
        )}
      </div>
    </div>
  );
}