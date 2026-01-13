/**
 * OPAL Real-time Events Client
 *
 * Provides SSE-based real-time updates for execution collaboration.
 * Handles step updates, user presence, and collaboration events.
 */

class OpalEvents {
    constructor() {
        this.eventSource = null;
        this.listeners = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.heartbeatInterval = null;
        this.currentActivity = null;
    }

    /**
     * Connect to the SSE event stream
     */
    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        const userId = localStorage.getItem('opal_user_id');
        if (!userId) {
            console.warn('OpalEvents: No user ID set, skipping SSE connection');
            return;
        }

        const url = `/api/events/stream`;
        this.eventSource = new EventSource(url);

        this.eventSource.onopen = () => {
            console.log('OpalEvents: Connected to event stream');
            this.reconnectAttempts = 0;
            this.emit('connected');
        };

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleEvent(data);
            } catch (e) {
                console.error('OpalEvents: Failed to parse event', e);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('OpalEvents: Connection error', error);
            this.eventSource.close();
            this.eventSource = null;
            this.emit('disconnected');
            this.attemptReconnect();
        };

        // Start heartbeat
        this.startHeartbeat();
    }

    /**
     * Disconnect from the SSE event stream
     */
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.stopHeartbeat();
        this.emit('disconnected');
    }

    /**
     * Attempt to reconnect after connection failure
     */
    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.warn('OpalEvents: Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

        console.log(`OpalEvents: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
    }

    /**
     * Handle incoming events
     */
    handleEvent(event) {
        const { type, data, timestamp } = event;

        // Emit to specific listeners
        this.emit(type, data, timestamp);

        // Emit to global 'event' listener
        this.emit('event', event);
    }

    /**
     * Add event listener
     */
    on(eventType, callback) {
        if (!this.listeners[eventType]) {
            this.listeners[eventType] = [];
        }
        this.listeners[eventType].push(callback);
        return () => this.off(eventType, callback);
    }

    /**
     * Remove event listener
     */
    off(eventType, callback) {
        if (this.listeners[eventType]) {
            this.listeners[eventType] = this.listeners[eventType].filter(cb => cb !== callback);
        }
    }

    /**
     * Emit event to listeners
     */
    emit(eventType, ...args) {
        const callbacks = this.listeners[eventType] || [];
        callbacks.forEach(cb => {
            try {
                cb(...args);
            } catch (e) {
                console.error(`OpalEvents: Error in ${eventType} listener`, e);
            }
        });
    }

    /**
     * Start periodic heartbeat
     */
    startHeartbeat() {
        this.stopHeartbeat();

        // Send heartbeat every 15 seconds
        this.heartbeatInterval = setInterval(() => {
            this.sendHeartbeat();
        }, 15000);

        // Send initial heartbeat
        this.sendHeartbeat();
    }

    /**
     * Stop heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    /**
     * Send heartbeat to server
     */
    async sendHeartbeat() {
        const userId = localStorage.getItem('opal_user_id');
        if (!userId) return;

        try {
            const response = await fetch('/api/users/heartbeat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Id': userId,
                },
                body: JSON.stringify({
                    activity: this.currentActivity,
                }),
            });

            if (!response.ok) {
                console.warn('OpalEvents: Heartbeat failed', response.status);
            }
        } catch (e) {
            console.error('OpalEvents: Heartbeat error', e);
        }
    }

    /**
     * Update current activity (shown to other users)
     */
    setActivity(activity) {
        this.currentActivity = activity;
        this.sendHeartbeat();
    }

    /**
     * Check if connected
     */
    get isConnected() {
        return this.eventSource && this.eventSource.readyState === EventSource.OPEN;
    }
}

// Global instance
window.opalEvents = new OpalEvents();

// Auto-connect on page load if user is set
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('opal_user_id')) {
        window.opalEvents.connect();
    }
});

// Disconnect on page unload
window.addEventListener('beforeunload', () => {
    window.opalEvents.disconnect();
});


/**
 * Execution collaboration helper
 */
class ExecutionCollaboration {
    constructor(instanceId) {
        this.instanceId = instanceId;
        this.participants = [];
        this.setupEventListeners();
    }

    /**
     * Setup SSE event listeners for this execution
     */
    setupEventListeners() {
        // Step events
        window.opalEvents.on('step_started', (data) => {
            if (data.instance_id === this.instanceId) {
                this.onStepStarted(data);
            }
        });

        window.opalEvents.on('step_completed', (data) => {
            if (data.instance_id === this.instanceId) {
                this.onStepCompleted(data);
            }
        });

        // User events
        window.opalEvents.on('user_joined', (data) => {
            if (data.instance_id === this.instanceId) {
                this.onUserJoined(data);
            }
        });

        window.opalEvents.on('user_left', (data) => {
            if (data.instance_id === this.instanceId) {
                this.onUserLeft(data);
            }
        });

        // Instance completion
        window.opalEvents.on('instance_completed', (data) => {
            if (data.instance_id === this.instanceId) {
                this.onInstanceCompleted(data);
            }
        });
    }

    /**
     * Join this execution
     */
    async join() {
        const userId = localStorage.getItem('opal_user_id');
        if (!userId) return;

        try {
            const response = await fetch(`/api/procedure-instances/${this.instanceId}/join`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Id': userId,
                },
            });

            if (response.ok) {
                const data = await response.json();
                this.updateParticipants(data.participants);
                window.opalEvents.setActivity(`executing:${this.instanceId}`);
            }
        } catch (e) {
            console.error('ExecutionCollaboration: Failed to join', e);
        }
    }

    /**
     * Leave this execution
     */
    async leave() {
        const userId = localStorage.getItem('opal_user_id');
        if (!userId) return;

        try {
            await fetch(`/api/procedure-instances/${this.instanceId}/leave`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Id': userId,
                },
            });

            window.opalEvents.setActivity(null);
        } catch (e) {
            console.error('ExecutionCollaboration: Failed to leave', e);
        }
    }

    /**
     * Load current participants
     */
    async loadParticipants() {
        try {
            const response = await fetch(`/api/procedure-instances/${this.instanceId}/participants`, {
                headers: {
                    'X-User-Id': localStorage.getItem('opal_user_id') || '',
                },
            });

            if (response.ok) {
                const data = await response.json();
                this.updateParticipants(data.participants);
            }
        } catch (e) {
            console.error('ExecutionCollaboration: Failed to load participants', e);
        }
    }

    /**
     * Update participants display
     */
    updateParticipants(participants) {
        this.participants = participants;
        this.renderParticipants();
    }

    /**
     * Render participants UI
     */
    renderParticipants() {
        const container = document.getElementById('participants-list');
        if (!container) return;

        container.innerHTML = this.participants.map(p => `
            <div class="participant" data-user-id="${p.user_id}">
                <span class="participant-avatar">${p.user_name.charAt(0).toUpperCase()}</span>
                <span class="participant-name">${p.user_name}</span>
                ${p.last_step ? `<span class="participant-step">Step ${p.last_step}</span>` : ''}
            </div>
        `).join('');
    }

    /**
     * Handle step started event
     */
    onStepStarted(data) {
        const stepEl = document.getElementById(`step-${data.step_number}`) ||
                       document.getElementById(`op-${data.step_number}`);

        if (stepEl) {
            // Update status indicator
            const statusEl = stepEl.querySelector('.status');
            if (statusEl) {
                statusEl.className = 'status status-info';
                statusEl.textContent = 'IN PROGRESS';
            }

            // Show who started it (if not current user)
            const currentUserId = parseInt(localStorage.getItem('opal_user_id'));
            if (data.user_id !== currentUserId && data.user_name) {
                this.showStepActivity(stepEl, `${data.user_name} started this step`);
            }
        }

        // Flash notification
        this.showNotification(`Step ${data.step_number} started${data.user_name ? ` by ${data.user_name}` : ''}`);
    }

    /**
     * Handle step completed event
     */
    onStepCompleted(data) {
        const stepEl = document.getElementById(`step-${data.step_number}`) ||
                       document.getElementById(`op-${data.step_number}`);

        if (stepEl) {
            // Update status indicator
            const statusEl = stepEl.querySelector('.status');
            if (statusEl) {
                statusEl.className = 'status status-ok';
                statusEl.textContent = 'COMPLETED';
            }

            // Hide buttons
            const actionsEl = stepEl.querySelector('.step-actions');
            if (actionsEl) {
                const buttons = actionsEl.querySelectorAll('button');
                buttons.forEach(btn => btn.style.display = 'none');
            }
        }

        // Flash notification
        const currentUserId = parseInt(localStorage.getItem('opal_user_id'));
        if (data.user_id !== currentUserId) {
            this.showNotification(`Step ${data.step_number} completed${data.user_name ? ` by ${data.user_name}` : ''}`);
        }

        // Update progress
        this.updateProgress();
    }

    /**
     * Handle user joined event
     */
    onUserJoined(data) {
        const currentUserId = parseInt(localStorage.getItem('opal_user_id'));
        if (data.user_id !== currentUserId) {
            this.showNotification(`${data.user_name} joined the execution`);
        }
        this.loadParticipants();
    }

    /**
     * Handle user left event
     */
    onUserLeft(data) {
        this.showNotification(`${data.user_name} left the execution`);
        this.loadParticipants();
    }

    /**
     * Handle instance completed event
     */
    onInstanceCompleted(data) {
        this.showNotification('Execution completed!');
        // Reload page to show final state
        setTimeout(() => window.location.reload(), 1000);
    }

    /**
     * Show activity indicator on a step
     */
    showStepActivity(stepEl, message) {
        let activityEl = stepEl.querySelector('.step-activity');
        if (!activityEl) {
            activityEl = document.createElement('div');
            activityEl.className = 'step-activity';
            stepEl.appendChild(activityEl);
        }
        activityEl.textContent = message;
        activityEl.style.display = 'block';

        // Hide after 5 seconds
        setTimeout(() => {
            activityEl.style.display = 'none';
        }, 5000);
    }

    /**
     * Show notification toast
     */
    showNotification(message) {
        // Create or get notification container
        let container = document.getElementById('notification-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            document.body.appendChild(container);
        }

        // Create notification element
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        container.appendChild(notification);

        // Remove after animation
        setTimeout(() => {
            notification.classList.add('fade-out');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    /**
     * Update progress display
     */
    updateProgress() {
        // This would require tracking step states client-side
        // For now, just suggest a refresh might be needed
        const progressEl = document.querySelector('.panel-body [style*="font-size: 2rem"]');
        if (progressEl) {
            progressEl.style.opacity = '0.7';
        }
    }
}

// Export for use
window.ExecutionCollaboration = ExecutionCollaboration;
