// SPDX-License-Identifier: GPL-3.0-or-later
package com.termux.app;

import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import android.system.Os;
import com.termux.terminal.TerminalSession;
import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;
import org.json.JSONObject;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

final class TermuxTerminalControl {
    static final String SCHEMA = "termux-terminal-origin-v1";
    private final TermuxService service;
    TermuxTerminalControl(TermuxService service) { this.service = service; }
    String execute(String[] args, int peerPid, int peerUid) throws Exception {
        if (peerUid != android.os.Process.myUid() || args.length < 2)
            throw new IllegalArgumentException("terminal control unavailable");
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<String> reply = new AtomicReference<>();
        AtomicReference<Exception> failure = new AtomicReference<>();
        AtomicBoolean expired = new AtomicBoolean(false);
        long deadline = SystemClock.uptimeMillis() + 2000;
        service.runTerminalControl(() -> {
            try {
                if (expired.get() || SystemClock.uptimeMillis() >= deadline)
                    throw new IllegalStateException("terminal control expired");
                JSONObject result = new JSONObject().put("schema", SCHEMA);
                if (args.length == 2 && args[1].equals("capabilities")) {
                    result.put("operations", "origin,validate,focus");
                } else if (args.length == 2 && args[1].equals("origin")) {
                    JSONObject origin = origin(peerPid, peerUid);
                    result.put("origin", origin);
                    TerminalSession target = service.getTerminalSessionForHandle(origin.getString("handle"));
                    result.put("selected", service.isSelectedTerminal(target));
                } else if (args.length == 5 && (args[1].equals("validate") || args[1].equals("focus"))) {
                    TerminalSession target = validate(args[2], args[3], args[4]);
                    long start = TerminalProcessIdentity.read(target.getPid()).start;
                    if (args[1].equals("focus")) {
                        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(service))
                            throw new IllegalStateException("terminal focus permission unavailable");
                        if (expired.get() || SystemClock.uptimeMillis() >= deadline)
                            throw new IllegalStateException("terminal control expired");
                        service.focusExistingTerminal(target);
                    }
                    result.put("origin", reference(target, start));
                    result.put("selected", service.isSelectedTerminal(target));
                } else throw new IllegalArgumentException("invalid terminal control request");
                reply.set(result.put("terminal_count", service.getTermuxSessionsSize()).put("result", "ok").toString() + "\n");
            } catch (Exception e) { failure.set(e); }
            finally { completed.countDown(); }
        });
        if (!completed.await(2, TimeUnit.SECONDS)) {
            expired.set(true);
            throw new IllegalStateException("terminal control expired");
        }
        if (failure.get() != null) throw failure.get();
        return reply.get();
    }
    private JSONObject origin(int pid, int uid) throws Exception {
        TerminalProcessIdentity original = TerminalProcessIdentity.read(pid);
        int cursor = pid;
        TerminalSession found = null;
        long foundStart = 0;
        for (int depth = 0; depth < 64 && cursor > 0; depth++) {
            if (Os.stat("/proc/" + cursor).st_uid != uid) break;
            TerminalProcessIdentity identity = TerminalProcessIdentity.read(cursor);
            for (TermuxSession session : service.getTermuxSessions()) {
                TerminalSession terminal = session.getTerminalSession();
                if (terminal.isRunning() && terminal.getPid() == cursor) {
                    if (found != null) throw new IllegalStateException("ambiguous origin");
                    found = terminal; foundStart = identity.start;
                }
            }
            if (identity.parent == cursor) throw new IllegalStateException("invalid ancestry");
            cursor = identity.parent;
        }
        if (found == null || TerminalProcessIdentity.read(pid).start != original.start
            || !found.isRunning() || TerminalProcessIdentity.read(found.getPid()).start != foundStart)
            throw new IllegalStateException("origin unavailable");
        return reference(found, foundStart);
    }
    private TerminalSession validate(String handle, String pidValue, String startValue) throws Exception {
        if (!handle.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"))
            throw new IllegalArgumentException("invalid terminal reference");
        long pid = TerminalProcessIdentity.positive(pidValue);
        long start = TerminalProcessIdentity.positive(startValue);
        TerminalSession terminal = service.getTerminalSessionForHandle(handle);
        if (terminal == null || !terminal.isRunning() || terminal.getPid() != pid
            || TerminalProcessIdentity.read(terminal.getPid()).start != start)
            throw new IllegalStateException("origin unavailable");
        return terminal;
    }
    private JSONObject reference(TerminalSession terminal, long start) throws Exception {
        return new JSONObject().put("handle", terminal.mHandle).put("pid", terminal.getPid()).put("start", start);
    }
}
