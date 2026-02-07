import React from 'react';

export const TerminalHeader: React.FC = () => {
  return (
    <div className="flex items-center justify-between p-2 border-b border-border bg-[#161616]">
      <div className="flex items-center space-x-2">
        <span className="text-primary font-bold">ENTROCUT_v0.1.0-mock</span>
        <span className="text-border">|</span>
        <span className="text-xs text-foreground/50">SYSTEM_READY</span>
      </div>
      <div className="flex space-x-2">
        <div className="w-3 h-3 bg-border" />
        <div className="w-3 h-3 bg-border" />
        <div className="w-3 h-3 bg-primary" />
      </div>
    </div>
  );
};
