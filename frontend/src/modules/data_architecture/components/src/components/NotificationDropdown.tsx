import type { Notification } from '../types';

interface NotificationDropdownProps {
  notifications: Notification[];
  isOpen: boolean;
  onClose: () => void;
  onNotificationClick?: (table: string) => void;
}

export function NotificationDropdown({ notifications, isOpen, onClose, onNotificationClick }: NotificationDropdownProps) {
  if (!isOpen) return null;

  const unreadNotifications = notifications.filter(
    (n) => n.type === 'approval' || n.type === 'quarantine'
  );

  return (
    <div className="notification-dropdown">
      <div className="notification-header">
        <span>Notifications ({unreadNotifications.length})</span>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
      <div className="notification-list">
        {unreadNotifications.length === 0 ? (
          <div className="notification-item empty">
            <span className="notif-icon">✓</span>
            <span>No pending notifications</span>
          </div>
        ) : (
          unreadNotifications.map((notif, idx) => (
            <div 
              key={idx} 
              className={`notification-item type-${notif.type}`}
              onClick={() => {
                if (onNotificationClick && notif.table) {
                  onNotificationClick(notif.table);
                  onClose();
                }
              }}
              style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              <div className="notif-icon">
                {notif.type === 'approval' ? '✓' : notif.type === 'quarantine' ? '⚠️' : 'ℹ️'}
              </div>
              <div className="notif-content">
                <div className="notif-table">{notif.table}</div>
                <div className="notif-reason">{notif.reason}</div>
                <div className="notif-time">{notif.timestamp}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
