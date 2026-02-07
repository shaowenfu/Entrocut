import React, { useState } from 'react';
import { Upload, FileVideo } from 'lucide-react';

interface VideoUploaderProps {
  onStart: (path: string) => void;
  disabled: boolean;
}

export const VideoUploader: React.FC<VideoUploaderProps> = ({ onStart, disabled }) => {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const handleSelect = async () => {
    const path = await window.electron.file.selectVideo();
    if (path) {
      setSelectedPath(path);
    }
  };

  return (
    <div className="p-6 border border-dashed border-border flex flex-col items-center justify-center space-y-4">
      {selectedPath ? (
        <div className="flex flex-col items-center space-y-2 w-full">
          <FileVideo className="w-12 h-12 text-primary" />
          <div className="text-xs truncate max-w-full text-foreground/70">{selectedPath}</div>
          <div className="flex space-x-2 pt-4">
            <button className="btn" onClick={() => setSelectedPath(null)} disabled={disabled}>CHANGE</button>
            <button className="btn btn-primary" onClick={() => onStart(selectedPath)} disabled={disabled}>
              START_JOB
            </button>
          </div>
        </div>
      ) : (
        <button 
          className="flex flex-col items-center space-y-2 p-8 hover:bg-white/5 transition-colors w-full"
          onClick={handleSelect}
          disabled={disabled}
        >
          <Upload className="w-12 h-12 text-foreground/30" />
          <span className="text-sm font-bold">SELECT_SOURCE_VIDEO</span>
          <span className="text-xs text-foreground/50">MP4, MKV, MOV (LOCAL_ONLY)</span>
        </button>
      )}
    </div>
  );
};
