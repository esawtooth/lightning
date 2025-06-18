flowchart TD
    %% daily_email_summary - acyclic workflow

    event_email_check["event.email.check\n(time.interval)\nPT1H"]
    style event_email_check fill:#e1f5fe

    summarize_emails["summarize_emails\n[llm.summarize]"]
    style summarize_emails fill:#fff3e0
    send_teams_notification["send_teams_notification\n[chat.sendTeamsMessage]"]
    style send_teams_notification fill:#fff3e0

    event_summary_ready["event.summary_ready"]
    style event_summary_ready fill:#f3e5f5
    event_notification_sent["event.notification_sent"]
    style event_notification_sent fill:#f3e5f5

    event_email_check --> summarize_emails
    summarize_emails --> event_summary_ready
    event_summary_ready --> send_teams_notification
    send_teams_notification --> event_notification_sent