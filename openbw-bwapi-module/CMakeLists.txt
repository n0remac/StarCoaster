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

include(CTest)
if(BUILD_TESTING)
  add_executable(world_state_test tests/world_state_test.cpp)
  target_include_directories(world_state_test PRIVATE src)
  add_test(NAME world_state_test COMMAND world_state_test)
  add_executable(world_navigation_test tests/world_navigation_test.cpp)
  target_include_directories(world_navigation_test PRIVATE src)
  add_test(NAME world_navigation_test COMMAND world_navigation_test)
endif()
