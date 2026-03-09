import React from 'react';
import type { DashboardSummaryResponse } from '../types';
import { Panel } from '../panels/Panel';
import { MetricCard } from '../cards/MetricCard';

interface TimelinePageProps {
  summary: DashboardSummaryResponse;
}

const TimelinePage: React.FC<TimelinePageProps> = ({ summary }) => {
  const { timeline } = summary;

  // Calculate summary metrics
  const totalRecordsProcessed = timeline.reduce((sum, evt) => sum + evt.records_processed, 0);
  const uniqueDatasets = new Set(timeline.map((evt) => evt.dataset)).size;

  return (
    <div className="grid-12 animate-fade page-grid">
      {/* Timeline Metrics Row */}
      <div className="span-4">
        <MetricCard
          label="Timeline Events"
          value={timeline.length}
          hint="Recent operations"
          tone="neutral"
        />
      </div>
      <div className="span-4">
        <MetricCard
          label="Records Processed"
          value={totalRecordsProcessed}
          hint="Across all events"
          tone="positive"
        />
      </div>
      <div className="span-4">
        <MetricCard
          label="Unique Datasets"
          value={uniqueDatasets}
          hint="Involved in events"
          tone="neutral"
        />
      </div>

      {/* Timeline Event Stream */}
      <div className="span-12">
        <Panel title="Pipeline Timeline" subtitle={`${timeline.length} events (newest first)`}>
          <div className="table-scroll table-scroll-tall">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Operation</th>
                  <th>Dataset</th>
                  <th>Records Processed</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {timeline.length > 0 ? (
                  timeline.map((event, idx) => (
                    <tr key={idx}>
                      <td>{new Date(event.timestamp).toLocaleString()}</td>
                      <td>
                        <span
                          style={{
                            padding: '0.25rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.8rem',
                            backgroundColor:
                              event.operation.includes('ingestion') ? '#dbeafe' :
                              event.operation.includes('silver') ? '#fef3c7' :
                              event.operation.includes('gold') ? '#d1fae5' : '#f3f4f6',
                            color:
                              event.operation.includes('ingestion') ? '#1e40af' :
                              event.operation.includes('silver') ? '#92400e' :
                              event.operation.includes('gold') ? '#065f46' : '#374151',
                          }}
                        >
                          {event.operation}
                        </span>
                      </td>
                      <td>{event.dataset}</td>
                      <td>{event.records_processed.toLocaleString()}</td>
                      <td>
                        <span
                          style={{
                            color: '#10b981',
                            fontWeight: 500,
                            fontSize: '0.85rem',
                          }}
                        >
                          completed
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr className="loading-row">
                    <td colSpan={5}>No timeline events available</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
};

export { TimelinePage };
