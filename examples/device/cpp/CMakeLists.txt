cmake_minimum_required(VERSION 3.14)
project(iot_device_client CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 依赖：IXWebSocket、nlohmann_json、OpenSSL
#   Ubuntu: sudo apt install libssl-dev zlib1g-dev nlohmann-json3-dev
#   IXWebSocket: git clone https://github.com/machinezone/IXWebSocket && cd IXWebSocket \
#                && cmake -B build -DUSE_TLS=1 && cmake --build build -j && sudo cmake --install build
find_package(ixwebsocket CONFIG REQUIRED)
find_package(nlohmann_json 3.2 CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(ZLIB REQUIRED)
find_package(Threads REQUIRED)

add_executable(device_client device_client.cpp)
target_link_libraries(device_client PRIVATE ixwebsocket::ixwebsocket nlohmann_json::nlohmann_json
                      OpenSSL::Crypto OpenSSL::SSL ZLIB::ZLIB Threads::Threads)
