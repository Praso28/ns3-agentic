/*
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include "ns3/core-module.h"
#include "ns3/applications-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("Ai5gMetrics");

namespace
{

class MetricsEngine
{
  public:
    void Configure(bool metricsToStdout,
                   std::string controlChannel,
                   uint32_t durationSeconds,
                   bool enableDefaultFaults,
                   bool clearControlAtStart,
                   uint32_t seed)
    {
        m_metricsToStdout = metricsToStdout;
        m_controlChannel = std::move(controlChannel);
        m_durationSeconds = durationSeconds;
        m_enableDefaultFaults = enableDefaultFaults;
                m_seed = seed;

        // Start with healthy network state.
        m_nodeUp = true;
        m_loadMultiplier = 1.0;
        m_degradation = 0.0;

        if (clearControlAtStart && !m_controlChannel.empty())
        {
            std::ofstream out(m_controlChannel, std::ios::trunc);
            (void)out;
        }

        BuildNetwork();
    }

    void Start()
    {
        Simulator::Stop(Seconds(static_cast<double>(m_durationSeconds + 2)));
        ScheduleTick();
    }

  private:
    struct SnapshotTotals
    {
        uint64_t txPackets{0};
        uint64_t rxPackets{0};
        uint64_t txBytes{0};
        uint64_t rxBytes{0};
        Time delaySum{Seconds(0.0)};
        Time jitterSum{Seconds(0.0)};
    };

    void ScheduleTick()
    {
        if (m_nowSeconds > m_durationSeconds)
        {
            Simulator::Stop();
            return;
        }

        Simulator::Schedule(Seconds(1.0), &MetricsEngine::Tick, this);
    }

    static std::string ExtractQuoted(const std::string& line, const std::string& key)
    {
        const std::string token = "\"" + key + "\"";
        auto keyPos = line.find(token);
        if (keyPos == std::string::npos)
        {
            return "";
        }

        auto colonPos = line.find(':', keyPos + token.size());
        if (colonPos == std::string::npos)
        {
            return "";
        }

        auto firstQuote = line.find('"', colonPos + 1);
        if (firstQuote == std::string::npos)
        {
            return "";
        }

        auto secondQuote = line.find('"', firstQuote + 1);
        if (secondQuote == std::string::npos)
        {
            return "";
        }

        return line.substr(firstQuote + 1, secondQuote - firstQuote - 1);
    }

    static double ExtractPayloadFactor(const std::string& line, double fallback)
    {
        auto payloadPos = line.find("\"factor\"");
        if (payloadPos == std::string::npos)
        {
            return fallback;
        }

        auto colonPos = line.find(':', payloadPos);
        if (colonPos == std::string::npos)
        {
            return fallback;
        }

        std::size_t endPos = colonPos + 1;
        while (endPos < line.size() && (line[endPos] == ' ' || line[endPos] == '\t'))
        {
            ++endPos;
        }

        std::size_t parseEnd = endPos;
        while (parseEnd < line.size() &&
               (std::isdigit(static_cast<unsigned char>(line[parseEnd])) || line[parseEnd] == '.' ||
                line[parseEnd] == '-' || line[parseEnd] == '+'))
        {
            ++parseEnd;
        }

        if (parseEnd <= endPos)
        {
            return fallback;
        }

        return std::stod(line.substr(endPos, parseEnd - endPos));
    }

    void ApplyControlActions()
    {
        if (m_controlChannel.empty())
        {
            return;
        }

        std::ifstream in(m_controlChannel);
        if (!in.is_open())
        {
            return;
        }

        std::string line;
        uint64_t index = 0;
        while (std::getline(in, line))
        {
            if (index++ < m_controlLineCursor)
            {
                continue;
            }

            std::string action = ExtractQuoted(line, "action");
            if (action == "restart_node")
            {
                m_nodeUp = true;
                m_nodeFailureRemaining = 0;
            }
            else if (action == "reduce_load")
            {
                const double factor = ExtractPayloadFactor(line, 0.30);
                m_loadMultiplier = std::max(1.0, m_loadMultiplier * (1.0 - factor));
                if (m_loadMultiplier <= 1.01)
                {
                    m_loadSpikeRemaining = 0;
                    m_loadMultiplier = 1.0;
                }
            }

            m_controlLineCursor++;
        }
    }

    void ApplyDefaultFaultTimeline()
    {
        if (!m_enableDefaultFaults)
        {
            return;
        }

        // Traffic spike first (F2), then mild degradation (F3), then node outage (F1).
        if (m_nowSeconds == 22)
        {
            m_loadSpikeRemaining = 18;
            m_loadMultiplier = 2.2;
        }

        if (m_nowSeconds == 58)
        {
            m_degradationRemaining = 18;
            m_degradation = 0.06;
        }

        if (m_nowSeconds == 90)
        {
            m_nodeFailureRemaining = 12;
            m_nodeUp = false;
        }
    }

    void DecayFaultStates()
    {
        if (m_loadSpikeRemaining > 0)
        {
            --m_loadSpikeRemaining;
            if (m_loadSpikeRemaining == 0)
            {
                m_loadMultiplier = 1.0;
            }
        }

        if (m_degradationRemaining > 0)
        {
            --m_degradationRemaining;
            if (m_degradationRemaining == 0)
            {
                m_degradation = 0.0;
            }
        }

        if (m_nodeFailureRemaining > 0)
        {
            --m_nodeFailureRemaining;
            if (m_nodeFailureRemaining == 0)
            {
                m_nodeUp = true;
            }
        }
    }

    void BuildNetwork()
    {
        RngSeedManager::SetSeed(1);
        RngSeedManager::SetRun(m_seed);

        m_nodes.Create(2);

        PointToPointHelper p2p;
        p2p.SetDeviceAttribute("DataRate", StringValue("120Mbps"));
        p2p.SetChannelAttribute("Delay", StringValue("12ms"));
        p2p.SetQueue("ns3::DropTailQueue", "MaxSize", StringValue("600p"));
        m_devices = p2p.Install(m_nodes);

        InternetStackHelper internet;
        internet.Install(m_nodes);

        Ipv4AddressHelper ipv4;
        ipv4.SetBase("10.1.1.0", "255.255.255.0");
        m_interfaces = ipv4.Assign(m_devices);

        PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                    InetSocketAddress(Ipv4Address::GetAny(), m_sinkPort));
        m_sinkApps = sinkHelper.Install(m_nodes.Get(1));
        m_sinkApps.Start(Seconds(0.2));
        m_sinkApps.Stop(Seconds(static_cast<double>(m_durationSeconds + 2)));

        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(m_interfaces.GetAddress(1), m_sinkPort));
        onoff.SetAttribute("PacketSize", UintegerValue(1200));
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        onoff.SetAttribute("DataRate", DataRateValue(DataRate("65Mbps")));

        m_sourceApps = onoff.Install(m_nodes.Get(0));
        m_sourceApps.Start(Seconds(1.0));
        m_sourceApps.Stop(Seconds(static_cast<double>(m_durationSeconds + 2)));

        m_onOff = DynamicCast<OnOffApplication>(m_sourceApps.Get(0));

        m_errorModel = CreateObject<RateErrorModel>();
        m_errorModel->SetAttribute("ErrorUnit", EnumValue(RateErrorModel::ERROR_UNIT_PACKET));
        m_errorModel->SetAttribute("ErrorRate", DoubleValue(0.0));
        m_devices.Get(1)->SetAttribute("ReceiveErrorModel", PointerValue(m_errorModel));

        m_flowMonitor = m_flowMonitorHelper.InstallAll();
        m_flowClassifier = DynamicCast<Ipv4FlowClassifier>(m_flowMonitorHelper.GetClassifier());
    }

    void ApplyNetworkState()
    {
        double offeredMbps = m_baseOfferedRateMbps * m_loadMultiplier;
        if (!m_nodeUp)
        {
            offeredMbps = 0.2;
        }
        offeredMbps = std::max(0.2, offeredMbps);

        const uint64_t bps = static_cast<uint64_t>(offeredMbps * 1000000.0);
        if (m_onOff != nullptr)
        {
            m_onOff->SetAttribute("DataRate", DataRateValue(DataRate(bps)));
        }

        const double loadPressure = std::max(0.0, (offeredMbps / m_linkCapacityMbps) - 1.0);
        double lossRate = 0.001 + m_degradation + 0.02 * loadPressure;
        if (!m_nodeUp)
        {
            lossRate = 1.0;
        }
        lossRate = std::clamp(lossRate, 0.0, 1.0);
        m_errorModel->SetAttribute("ErrorRate", DoubleValue(lossRate));
    }

    SnapshotTotals ReadTotals() const
    {
        SnapshotTotals totals;
        if (m_flowMonitor == nullptr || m_flowClassifier == nullptr)
        {
            return totals;
        }

        m_flowMonitor->CheckForLostPackets();
        auto stats = m_flowMonitor->GetFlowStats();
        for (const auto& kv : stats)
        {
            const auto flowId = kv.first;
            const auto& flowStats = kv.second;
            auto tuple = m_flowClassifier->FindFlow(flowId);
            if (tuple.destinationPort != m_sinkPort)
            {
                continue;
            }

            totals.txPackets += flowStats.txPackets;
            totals.rxPackets += flowStats.rxPackets;
            totals.txBytes += flowStats.txBytes;
            totals.rxBytes += flowStats.rxBytes;
            totals.delaySum += flowStats.delaySum;
            totals.jitterSum += flowStats.jitterSum;
        }

        return totals;
    }

    static double ToMilliSeconds(const Time& value)
    {
        return value.GetSeconds() * 1000.0;
    }

    void EmitMetrics()
    {
        const auto totals = ReadTotals();

        const uint64_t dTxPackets = totals.txPackets - m_prevTotals.txPackets;
        const uint64_t dRxPackets = totals.rxPackets - m_prevTotals.rxPackets;
        const uint64_t dTxBytes = totals.txBytes - m_prevTotals.txBytes;
        const uint64_t dRxBytes = totals.rxBytes - m_prevTotals.rxBytes;
        const Time dDelay = totals.delaySum - m_prevTotals.delaySum;
        const Time dJitter = totals.jitterSum - m_prevTotals.jitterSum;

        double throughput = static_cast<double>(dRxBytes) * 8.0 / 1000000.0;
        double packetLoss = 0.0;
        if (dTxPackets > 0)
        {
            packetLoss = static_cast<double>(dTxPackets - std::min(dTxPackets, dRxPackets)) /
                         static_cast<double>(dTxPackets);
        }

        double latency = m_lastLatencyMs;
        double jitter = m_lastJitterMs;
        if (dRxPackets > 0)
        {
            latency = ToMilliSeconds(dDelay) / static_cast<double>(dRxPackets);
            jitter = ToMilliSeconds(dJitter) / static_cast<double>(std::max<uint64_t>(1, dRxPackets - 1));
            m_lastLatencyMs = latency;
            m_lastJitterMs = jitter;
        }

        const uint64_t backlogBytes = (dTxBytes > dRxBytes) ? (dTxBytes - dRxBytes) : 0;
        const double backlogQueueDelayMs =
            (static_cast<double>(backlogBytes) * 8.0 / (m_linkCapacityMbps * 1000000.0)) * 1000.0;
        const double queueDelay = std::max(0.0, latency - m_linkBaseDelayMs) + backlogQueueDelayMs;

        packetLoss = std::clamp(packetLoss, 0.0, 1.0);
        throughput = std::max(0.0, throughput);
        latency = std::max(0.0, latency);
        jitter = std::max(0.0, jitter);

        if (m_metricsToStdout)
        {
            std::ostringstream out;
            out << std::fixed << std::setprecision(6)
                << "{"
                << "\"timestamp\":" << m_nowSeconds << ","
                << "\"latency\":" << latency << ","
                << "\"throughput\":" << throughput << ","
                << "\"packet_loss\":" << packetLoss << ","
                << "\"jitter\":" << jitter << ","
                << "\"queue_delay\":" << queueDelay << ","
                << "\"node_id\":\"node-1\"," << "\"node_up\":" << (m_nodeUp ? "true" : "false")
                << "}";
            std::cout << out.str() << std::endl;
        }

        m_prevTotals = totals;
    }

    void Tick()
    {
        ApplyControlActions();
        ApplyDefaultFaultTimeline();
        ApplyNetworkState();
        EmitMetrics();
        DecayFaultStates();
        ++m_nowSeconds;
        ScheduleTick();
    }

    bool m_metricsToStdout{true};
    std::string m_controlChannel;
    uint32_t m_durationSeconds{180};
    bool m_enableDefaultFaults{true};
    uint32_t m_seed{7};

    bool m_nodeUp{true};
    double m_loadMultiplier{1.0};
    double m_degradation{0.0};
    double m_baseOfferedRateMbps{65.0};
    double m_linkCapacityMbps{120.0};
    double m_linkBaseDelayMs{12.0};
    double m_lastLatencyMs{20.0};
    double m_lastJitterMs{2.0};

    uint32_t m_nowSeconds{0};
    uint64_t m_controlLineCursor{0};
    uint32_t m_loadSpikeRemaining{0};
    uint32_t m_degradationRemaining{0};
    uint32_t m_nodeFailureRemaining{0};
    uint16_t m_sinkPort{9000};

    NodeContainer m_nodes;
    NetDeviceContainer m_devices;
    Ipv4InterfaceContainer m_interfaces;
    ApplicationContainer m_sourceApps;
    ApplicationContainer m_sinkApps;
    Ptr<OnOffApplication> m_onOff;
    Ptr<RateErrorModel> m_errorModel;
    FlowMonitorHelper m_flowMonitorHelper;
    Ptr<FlowMonitor> m_flowMonitor;
    Ptr<Ipv4FlowClassifier> m_flowClassifier;
    SnapshotTotals m_prevTotals;
};

} // namespace

int
main(int argc, char* argv[])
{
    bool metricsToStdout = true;
    bool enableDefaultFaults = true;
    bool clearControlAtStart = true;
    bool realTime = false;
    std::string controlChannel = "/tmp/ai5g-control.jsonl";
    uint32_t durationSeconds = 180;
    uint32_t seed = 7;

    CommandLine cmd(__FILE__);
    cmd.AddValue("metricsToStdout", "Emit metric JSON lines to stdout", metricsToStdout);
    cmd.AddValue("controlChannel", "Path to action command JSONL file", controlChannel);
    cmd.AddValue("durationSeconds", "Simulation duration in seconds", durationSeconds);
    cmd.AddValue("enableDefaultFaults", "Enable built-in combo fault timeline", enableDefaultFaults);
    cmd.AddValue("clearControlAtStart", "Truncate control channel at startup", clearControlAtStart);
    cmd.AddValue("realTime", "Run simulator in wall-clock real-time mode", realTime);
    cmd.AddValue("seed", "RNG stream seed", seed);
    cmd.Parse(argc, argv);

    if (realTime)
    {
        GlobalValue::Bind("SimulatorImplementationType", StringValue("ns3::RealtimeSimulatorImpl"));
    }

    MetricsEngine engine;
    engine.Configure(metricsToStdout,
                     controlChannel,
                     durationSeconds,
                     enableDefaultFaults,
                     clearControlAtStart,
                     seed);
    engine.Start();

    Simulator::Run();
    Simulator::Destroy();
    return 0;
}
