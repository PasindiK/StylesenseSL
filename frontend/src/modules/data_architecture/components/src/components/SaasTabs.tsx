import { motion } from 'framer-motion';

interface Tab {
  id: string;
  label: string;
}

interface SaasTabsProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

export function SaasTabs({ tabs, activeTab, onTabChange }: SaasTabsProps) {
  return (
    <div className="saas-tabs">
      <div className="tabs-container">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
            {activeTab === tab.id && (
              <motion.div
                className="tab-indicator"
                layoutId="tab-indicator"
                transition={{ type: 'spring', stiffness: 380, damping: 30 }}
              />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
