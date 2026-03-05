import { Calendar, Bell, User, X } from 'lucide-react';
import { useState } from 'react';

interface SaasHeaderProps {
  notificationCount: number;
  onNotificationClick: () => void;
}

export function SaasHeader({ notificationCount, onNotificationClick }: SaasHeaderProps) {
  const [dateRange, setDateRange] = useState('Last 7 Days');
  const [showCustomPicker, setShowCustomPicker] = useState(false);
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [appliedRange, setAppliedRange] = useState('Last 7 Days');

  const handleDateRangeChange = (value: string) => {
    setDateRange(value);
    if (value === 'Custom Range') {
      setShowCustomPicker(true);
    } else {
      setAppliedRange(value);
      setShowCustomPicker(false);
      console.log('Date range changed to:', value);
    }
  };

  const applyCustomRange = () => {
    if (customStartDate && customEndDate) {
      const formatted = `${customStartDate} to ${customEndDate}`;
      setAppliedRange(formatted);
      setShowCustomPicker(false);
      console.log('Custom date range applied:', formatted);
    }
  };

  const closeCustomPicker = () => {
    setShowCustomPicker(false);
    setDateRange(appliedRange);
  };

  return (
    <div className="saas-header">
      <div className="header-left">
        <div className="breadcrumb-nav">
          <span className="breadcrumb-item">Data Architecture</span>
          <span className="breadcrumb-sep">/</span>
          <span className="breadcrumb-item active">Overview</span>
        </div>
        <h1 className="page-title">Data Architecture</h1>
        <p className="page-subtitle">
          High-level architecture governance & schema lifecycle
          <span className="active-range-badge">{appliedRange}</span>
        </p>
      </div>

      <div className="header-right">
        <div className="date-range-selector">
          {/* @ts-ignore */}
          <Calendar size={16} />
          <select
            value={dateRange}
            onChange={(e) => handleDateRangeChange(e.target.value)}
            className="date-select"
          >
            <option value="Today">Today</option>
            <option value="Last 7 Days">Last 7 Days</option>
            <option value="Last 30 Days">Last 30 Days</option>
            <option value="Last 3 Months">Last 3 Months</option>
            <option value="Custom Range">Custom Range</option>
          </select>
        </div>

        {showCustomPicker && (
          <div className="custom-date-picker-overlay" onClick={closeCustomPicker}>
            <div className="custom-date-picker" onClick={(e) => e.stopPropagation()}>
              <div className="picker-header">
                <h3>Select Custom Date Range</h3>
                <button className="close-picker" onClick={closeCustomPicker}>
                  {/* @ts-ignore */}
                  <X size={18} />
                </button>
              </div>
              <div className="picker-body">
                <div className="date-input-group">
                  <label>Start Date</label>
                  <input
                    type="date"
                    value={customStartDate}
                    onChange={(e) => setCustomStartDate(e.target.value)}
                    className="date-input"
                  />
                </div>
                <div className="date-input-group">
                  <label>End Date</label>
                  <input
                    type="date"
                    value={customEndDate}
                    onChange={(e) => setCustomEndDate(e.target.value)}
                    className="date-input"
                  />
                </div>
              </div>
              <div className="picker-footer">
                <button className="btn-cancel" onClick={closeCustomPicker}>
                  Cancel
                </button>
                <button
                  className="btn-apply"
                  onClick={applyCustomRange}
                  disabled={!customStartDate || !customEndDate}
                >
                  Apply Range
                </button>
              </div>
            </div>
          </div>
        )}

        <button
          className="notification-btn"
          onClick={onNotificationClick}
          title="Notifications"
        >
          {/* @ts-ignore */}
          <Bell size={20} />
          {notificationCount > 0 && (
            <span className="notification-badge">{notificationCount}</span>
          )}
        </button>

        <div className="user-avatar">
          {/* @ts-ignore */}
          <User size={20} />
        </div>
      </div>
    </div>
  );
}
