import React, { useState, useEffect } from 'react';
import { Loader2, CheckCircle2, Play, Bot, ChevronDown, Sparkles, Scissors, Search, ScanSearch, RotateCcw } from 'lucide-react';
import './AgentChatPanels.css';

// ------------------------------
// UI Components
// ------------------------------

export const UserMessage = ({ text }: { text: string }) => (
  <div className="chat-bubble-user">
    {text}
  </div>
);

export const AgentFinalMessage = ({ text }: { text: string }) => (
  <div className="chat-bubble-agent">
    <Sparkles size={16} className="agent-sparkle" />
    <div className="agent-msg-content">{text}</div>
  </div>
);

/**
 * Breathing Agent Step
 * Automatically manages expansion based on loading status, but allows manual toggle.
 */
export const AgentStep = ({
  status,
  title,
  summary,
  thought,
  icon: Icon = CheckCircle2,
  children
}: {
  status: 'loading' | 'success';
  title: string;       // Shown when expanded
  summary: string;     // Shown when collapsed
  thought?: string;
  icon?: React.ElementType;
  children?: React.ReactNode;
}) => {
  // Default to expanded if loading, collapsed if success
  const [isExpanded, setIsExpanded] = useState(status === 'loading');

  useEffect(() => {
    if (status === 'success') {
      // Auto-collapse after a short delay so user can read the artifact
      const timer = setTimeout(() => {
        setIsExpanded(false);
      }, 1200);
      return () => clearTimeout(timer);
    } else if (status === 'loading') {
      setIsExpanded(true);
    }
  }, [status]);

  return (
    <div className={`agent-step ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <div className="agent-step-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className={`agent-step-icon ${status === 'loading' ? 'spinner' : 'success'}`}>
          {status === 'loading' ? <Loader2 size={14} /> : <Icon size={14} />}
        </div>
        <span className="step-title">{isExpanded ? title : summary}</span>
        <div className="step-chevron">
          <ChevronDown 
            size={14} 
            style={{ 
              transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', 
              transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)' 
            }} 
          />
        </div>
      </div>
      
      <div className={`agent-step-content-wrapper ${isExpanded ? 'expanded' : 'collapsed'}`}>
        <div className="agent-step-content-inner">
          <div className="agent-step-content">
            {thought && <div className="agent-thought">{thought}</div>}
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};

// ------------------------------
// Interactive Artifacts
// ------------------------------

export const RetrieveArtifact = ({ isLoading }: { isLoading?: boolean }) => {
  const cards = [
    { score: '98% Match', duration: '00:15', img: 'https://images.unsplash.com/photo-1495616811223-4d98c6e9c869?auto=format&fit=crop&w=300&q=80' },
    { score: '98% Match', duration: '00:15', img: 'https://images.unsplash.com/photo-1472214103451-9374bd1c798e?auto=format&fit=crop&w=300&q=80' },
    { score: '97% Match', duration: '00:15', img: 'https://images.unsplash.com/photo-1414445092210-91a5ea11a511?auto=format&fit=crop&w=300&q=80' },
    { score: '97% Match', duration: '00:15', img: 'https://images.unsplash.com/photo-1469122312224-c5846569feb1?auto=format&fit=crop&w=300&q=80' },
  ];

  if (isLoading) {
    return (
      <div className="clip-cards-grid">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="clip-card-mini" style={{ height: '70px' }}>
            <div className="skeleton-pulse" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="clip-cards-grid">
      {cards.map((card, i) => (
        <div key={i} className="clip-card-mini">
          <div className="clip-thumb-mini">
            <img src={card.img} alt="sunset thumbnail" />
            <span className="score-badge">{card.score}</span>
            <span className="duration-pill">{card.duration}</span>
          </div>
        </div>
      ))}
    </div>
  );
};

export const InspectArtifact = () => (
  <div className="inspect-artifact">
    <div className="inspect-frame">
      <img src="https://images.unsplash.com/photo-1472214103451-9374bd1c798e?auto=format&fit=crop&w=600&q=80" alt="inspecting" />
      <div className="inspect-scanline" />
      <div className="inspect-timecode">[00:08.500]</div>
    </div>
    <div className="inspect-report">
      <div className="inspect-report-row">
        <span className="inspect-report-label">[Camera]</span>
        <span className="inspect-report-value">Stable pan, smooth motion</span>
      </div>
      <div className="inspect-report-row">
        <span className="inspect-report-label">[Subject]</span>
        <span className="inspect-report-value">Sunset, High Contrast, Golden Hour</span>
      </div>
      <div className="inspect-report-row">
        <span className="inspect-report-label">[Flaws]</span>
        <span className="inspect-report-value" style={{color: '#f7b0b0'}}>Slight motion blur at end</span>
      </div>
    </div>
  </div>
);

export const PatchArtifact = () => (
  <div className="patch-artifact">
    <div className="patch-header">
      <Scissors size={12} /> Target: Video Track 1 @ 00:10.000
    </div>
    <div className="patch-body">
      <div className="patch-line inserted">+ [00:10:00 -&gt; 00:15:00] sunset_wide.mp4</div>
      <div className="patch-line removed">- [00:15:00 -&gt; 00:17:00] &lt;Empty Gap&gt;</div>
    </div>
  </div>
);

export const PreviewAction = () => (
  <div className="preview-action-wrapper">
    <button className="preview-btn">
      <Play size={16} fill="currentColor" />
      Play Draft Preview
    </button>
  </div>
);

// ------------------------------
// Layout & Orchestration
// ------------------------------

export const CopilotColumn = ({ children }: { children: React.ReactNode }) => (
  <div className="ai-copilot-column">
    <div className="ai-copilot-header">
      <h2>
        <Bot size={16} />
        <span>AI Copilot</span>
      </h2>
    </div>
    <div className="ai-copilot-body">
      {children}
    </div>
  </div>
);

/**
 * Simulation Canvas orchestrating the breathing flow.
 */
export const AgentChatPanels = () => {
  const [step, setStep] = useState(0);

  const resetSimulation = () => setStep(0);

  useEffect(() => {
    if (step === 0) {
      const timers = [
        setTimeout(() => setStep(1), 500),   // Start Retrieve
        setTimeout(() => setStep(2), 3000),  // End Retrieve, Start Inspect
        setTimeout(() => setStep(3), 6000),  // End Inspect, Start Patch
        setTimeout(() => setStep(4), 9000),  // End Patch, Show Final
      ];
      return () => timers.forEach(clearTimeout);
    }
  }, [step]);

  return (
    <div className="chat-canvas">
      <div className="sandbox-controls">
        <button onClick={resetSimulation}>
          <RotateCcw size={14} style={{display: 'inline', verticalAlign: 'text-bottom', marginRight: '6px'}}/> 
          Replay Breathing Flow Animation
        </button>
      </div>

      {/* Column 1: The Interactive Animated Flow */}
      <CopilotColumn>
        <UserMessage text="Interactive Demo: Find a sunset clip and cut it." />
        
        <div className="agent-execution-block">
          {step >= 1 && (
            <AgentStep 
              status={step === 1 ? 'loading' : 'success'}
              title="Retrieving clips for 'sunset'..."
              summary="✓ Found 4 relevant sunset clips"
              thought="I will search the media library for 'sunset' and fetch the top matches."
              icon={Search}
            >
              <RetrieveArtifact isLoading={step === 1} />
            </AgentStep>
          )}

          {step >= 2 && (
            <AgentStep 
              status={step === 2 ? 'loading' : 'success'}
              title="Inspecting clip stability and visual quality..."
              summary="✓ Inspected clip: stable pan, high contrast"
              thought="I need to ensure the selected clip has no severe jitter before adding it to the timeline."
              icon={ScanSearch}
            >
              <InspectArtifact />
            </AgentStep>
          )}

          {step >= 3 && (
            <AgentStep 
              status={step === 3 ? 'loading' : 'success'}
              title="Applying cuts to timeline..."
              summary="✓ Inserted sunset_wide.mp4 at 00:10.000"
              thought="The clip is good. I will patch the timeline by inserting the 5-second segment and removing the empty gap."
              icon={Scissors}
            >
              <PatchArtifact />
            </AgentStep>
          )}
        </div>

        {step >= 4 && (
          <>
            <AgentFinalMessage text="I found a beautiful, stable sunset clip and seamlessly cut it into your timeline at the 10-second mark. The gap has been removed. You can preview the result now!" />
            <PreviewAction />
          </>
        )}
      </CopilotColumn>

      {/* Column 2: Static Catalog - Expanded (Planning & Artifacts) */}
      <CopilotColumn>
        <UserMessage text="Static Catalog: All Steps Expanded" />
        <div className="agent-execution-block">
          <AgentStep status="loading" title="Retrieving clips for 'sunset'..." summary="✓ Found 4 relevant sunset clips" thought="I will search the media library for 'sunset' and fetch the top matches." icon={Search}>
            <RetrieveArtifact isLoading={false} />
          </AgentStep>
          <AgentStep status="loading" title="Inspecting clip stability and visual quality..." summary="✓ Inspected clip: stable pan, high contrast" thought="I need to ensure the selected clip has no severe jitter before adding it to the timeline." icon={ScanSearch}>
            <InspectArtifact />
          </AgentStep>
          <AgentStep status="loading" title="Applying cuts to timeline..." summary="✓ Inserted sunset_wide.mp4 at 00:10.000" thought="The clip is good. I will patch the timeline by inserting the 5-second segment and removing the empty gap." icon={Scissors}>
            <PatchArtifact />
          </AgentStep>
        </div>
      </CopilotColumn>

      {/* Column 3: Static Catalog - Final Collapsed State */}
      <CopilotColumn>
        <UserMessage text="Static Catalog: Final Collapsed State" />
        <div className="agent-execution-block">
          <AgentStep status="success" title="Retrieving clips for 'sunset'..." summary="✓ Found 4 relevant sunset clips" thought="I will search the media library for 'sunset' and fetch the top matches." icon={Search}>
            <RetrieveArtifact isLoading={false} />
          </AgentStep>
          <AgentStep status="success" title="Inspecting clip stability and visual quality..." summary="✓ Inspected clip: stable pan, high contrast" thought="I need to ensure the selected clip has no severe jitter before adding it to the timeline." icon={ScanSearch}>
            <InspectArtifact />
          </AgentStep>
          <AgentStep status="success" title="Applying cuts to timeline..." summary="✓ Inserted sunset_wide.mp4 at 00:10.000" thought="The clip is good. I will patch the timeline by inserting the 5-second segment and removing the empty gap." icon={Scissors}>
            <PatchArtifact />
          </AgentStep>
        </div>
        <AgentFinalMessage text="All tasks completed. You can preview the result now!" />
        <PreviewAction />
      </CopilotColumn>

    </div>
  );
};
