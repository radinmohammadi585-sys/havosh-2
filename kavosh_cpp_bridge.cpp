/*
 * Kavosh AI 2 — C++ Bridge Service (Bridge F / G endpoint)
 * Line-delimited JSON over TCP. Stdlib only (POSIX sockets).
 * Build: g++ -O2 -std=c++17 -o kavosh_cpp_bridge kavosh_cpp_bridge.cpp
 */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstring>
#include <iostream>
#include <string>
#include <sstream>
#include <chrono>

static const int PORT = 9101;

static std::string extract(const std::string& s, const std::string& key) {
    auto k = "\"" + key + "\"";
    auto p = s.find(k);
    if (p == std::string::npos) return "";
    p = s.find(':', p);
    if (p == std::string::npos) return "";
    p = s.find('"', p);
    if (p == std::string::npos) return "";
    auto e = s.find('"', p + 1);
    if (e == std::string::npos) return "";
    return s.substr(p + 1, e - p - 1);
}

static std::string handle(const std::string& line) {
    std::string rid = extract(line, "request_id");
    if (rid.empty()) rid = "unknown";
    std::string intent = extract(line, "intent");
    // lightweight "fast path" compute marker
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    std::ostringstream out;
    out << "{\"ok\":true,\"request_id\":\"" << rid
        << "\",\"service\":\"cpp\",\"bridge\":\"F\","
        << "\"payload\":{\"engine\":\"kavosh-cpp\",\"intent\":\"" << intent
        << "\",\"ts\":" << ms
        << ",\"note\":\"C++ bridge live\"}}";
    return out.str();
}

int main() {
    int server_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) { perror("socket"); return 1; }
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);
    if (bind(server_fd, (sockaddr*)&addr, sizeof(addr)) < 0) { perror("bind"); return 1; }
    if (listen(server_fd, 64) < 0) { perror("listen"); return 1; }
    std::cerr << "[kavosh-cpp] listening on " << PORT << std::endl;
    while (true) {
        sockaddr_in client{};
        socklen_t len = sizeof(client);
        int cfd = accept(server_fd, (sockaddr*)&client, &len);
        if (cfd < 0) continue;
        std::string buf;
        char tmp[1024];
        while (true) {
            ssize_t n = read(cfd, tmp, sizeof(tmp));
            if (n <= 0) break;
            buf.append(tmp, tmp + n);
            if (buf.find('\n') != std::string::npos) break;
            if (buf.size() > 1 << 20) break;
        }
        auto pos = buf.find('\n');
        std::string line = pos == std::string::npos ? buf : buf.substr(0, pos);
        std::string resp = handle(line) + "\n";
        write(cfd, resp.data(), resp.size());
        close(cfd);
    }
    return 0;
}
