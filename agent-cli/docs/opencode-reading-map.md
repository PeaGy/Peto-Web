# Bản đồ đọc OpenCode ngoại tuyến

Được tạo 17/10/2026 cho việc rà kiến trúc Peto. Mã nguồn đầy đủ của checkout nằm trong
[thư mục OpenCode](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode).
Clone chỉ lấy lịch sử một commit; nội dung tệp của commit đã có sẵn để tìm/đọc ngoại tuyến.

- Nguồn: [anomalyco/opencode](https://github.com/anomalyco/opencode).
- Nhánh `dev`, commit `22e771f5893e255ea78fc10557ed3fb98d3a1072`, phiên bản package `2.0.32`.
- [MIT LICENSE giữ nguyên](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/LICENSE).
- Metadata và chỉ mục dòng: [reference.json](C:/Users/binhb/Downloads/Peto-Web/.runtime/peto-opencode-review-20261017/reference.json),
  [source-index.json](C:/Users/binhb/Downloads/Peto-Web/.runtime/peto-opencode-review-20261017/source-index.json).

Đọc theo thứ tự dưới đây giúp nắm hợp đồng trước khi đi vào chi tiết. Tài liệu tóm lược cần được đối chiếu với
mã thực thi tại chính commit này; không lấy con số hay tên trường trong tài liệu cũ làm mặc định.

| Thứ tự | Cần hiểu | Tệp OpenCode | Đối ứng Peto |
|---|---|---|---|
| 1 | Ai sở hữu hợp đồng và trạng thái | [V2 overview](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/specs/v2/README.md) | [Kế hoạch CLI](C:/Users/binhb/Downloads/Peto-Web/PETO_AGENT_PLAN.md) |
| 2 | Nhận yêu cầu, thực thi, phục hồi | [Session contract](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/specs/v2/session.md) | [loop.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/loop.py) |
| 3 | Đầu vào/kết quả công cụ và quyền sở hữu | [Tools contract](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/specs/v2/tools.md) | [tools.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/tools.py) |
| 4 | Kiểm dữ liệu trước thực thi | [tool/runtime.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/tool/runtime.ts:63) | [tool_input.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/tool_input.py) |
| 5 | Tool call được lưu trước tác dụng phụ | [runner/step.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/runner/step.ts:104) | [_save_progress](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/loop.py) |
| 6 | Lời gọi dở dang không được phát lại | [runner/llm.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/runner/llm.ts:362) | [session_protocol.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/session_protocol.py) |
| 7 | Quyền chạy và quyền đọc đường dẫn | [permission.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/permission.ts), [file-access.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/file-access.ts) | [approvals.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/approvals.py), [workspace.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/workspace.py) |
| 8 | Shell và tác vụ nền | [shell tool](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/tool/plugin/shell.ts) | [runner.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/runner.py), [background.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/background.py) |
| 9 | Chọn model, instruction và tool snapshot | [session/context.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/context.ts) | [_step_context](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/loop.py), [Agent API](C:/Users/binhb/Downloads/Peto-Web/backend/features/agent/api.py) |
| 10 | Ngữ cảnh model và bản lưu đầy đủ | [compaction.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/compaction.ts) | [context.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/context.py), [recall.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/recall.py) |
| 11 | Lưu phiên, inbox và quyền điều phối | [store.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/store.ts), [inbox.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/inbox.ts), [execution.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/execution.ts) | [history.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/history.py), [screen.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/tui/screen.py) |
| 12 | Retry và trường hợp chưa rõ đã gửi hay chưa | [runner/retry.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/session/runner/retry.ts) | [client.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/client.py), [_attempt](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/loop.py) |
| 13 | Lưu output lớn và giới hạn phần gửi model | [tool-output.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/tool-output.ts) | [outputs.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/outputs.py) |
| 14 | Agent con có phiên riêng | [subagent tool](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/tool/plugin/subagent.ts) | [subagent.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/subagent.py) |
| 15 | UI tách khỏi việc công bố kết quả | [Event stream](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/specs/v2/event-stream-architecture.md) | [events.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/events.py), [presentation.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/presentation.py), [TerminalUI](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/tui/view.py) |
| 16 | Khôi phục tệp và giới hạn backup | [snapshot.ts](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/snapshot.ts) | [snapshot.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/snapshot.py) |
| 17 | Browser là một thành phần riêng | [Browser plugin](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/plugin-browser/README.md) | [browser.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/browser.py) |

Hướng dẫn kỹ thuật cạnh code: [Core Tool Architecture](C:/Users/binhb/Downloads/Peto-Web/.runtime/references/opencode/packages/core/src/tool/AGENTS.md).
Đó là tài liệu của repo tham chiếu; những quy định phát hành hay chạy script trong đó không tự trở thành yêu cầu của Peto.

Phần ghi phiên trên Windows của Peto có helper riêng:
[atomic_file.py](C:/Users/binhb/Downloads/Peto-Web/agent-cli/peto_agent/atomic_file.py). Probe trước/sau và các test
giới hạn retry được ghi trong báo cáo so sánh; đây là bản sửa từ bằng chứng trên máy, không sao chép nguyên runtime OpenCode.

Các regression test OpenCode đáng đọc nằm trong `packages/core/test/`: `tool-execute.test.ts`,
`tool-registry.test.ts`, `tool-output.test.ts`, `session-runner-tool-events.test.ts`, `session-execution.test.ts`,
`session-compaction.test.ts`, `session-instructions.test.ts`. Đây là code test để đối chiếu; đợt rà này không cài
dependency hoặc chạy OpenCode.

Khi tiếp tục công việc, bắt đầu từ [báo cáo so sánh](C:/Users/binhb/Downloads/Peto-Web/agent-cli/docs/opencode-harness-review-2026-10-17.md).
Không cần tìm web để đọc lại những nguồn đã liệt kê ở trên.
