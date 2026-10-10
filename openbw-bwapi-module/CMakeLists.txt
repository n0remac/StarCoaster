cmake_minimum_required(VERSION 3.16)
project(BridgeAIModule LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(BWAPI_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../upstream/bwapi" CACHE PATH "OpenBW BWAPI checkout")
set(BWAPI_BUILD_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../build/bwapi" CACHE PATH "OpenBW BWAPI build")

find_library(BWAPILIB_PATH NAMES BWAPILIB
  PATHS "${BWAPI_BUILD_DIR}/lib" NO_DEFAULT_PATH REQUIRED)

add_library(BridgeAIModule SHARED src/BridgeAIModule.cpp)
set_target_properties(BridgeAIModule PROPERTIES PREFIX "" BUILD_RPATH "${BWAPI_BUILD_DIR}/lib")
target_include_directories(BridgeAIModule PRIVATE "${BWAPI_SOURCE_DIR}/bwapi/include")
target_link_libraries(BridgeAIModule PRIVATE "${BWAPILIB_PATH}")
