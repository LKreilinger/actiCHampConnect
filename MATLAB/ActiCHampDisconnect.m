function ActiCHampDisconnect(proc, timeout)
% ACTICHAMPDISCONNECT Stop EEG_SharedMemoryProducer.exe and release the amplifier.
%   ActiCHampDisconnect(proc, timeout)
%
%   proc     process handle returned by ActiCHampConnect
%   timeout  seconds to wait before the process is killed (default 10)

if nargin < 2
    timeout = 10;
end
if isempty(proc) || proc.HasExited
    return;
end

% Ask the producer to stop (sets stopRequested in the shared memory).
try
    StopProducer();
catch
    warning('StopProducer failed, killing the producer.');
    proc.Kill();
end

if ~proc.WaitForExit(round(timeout * 1000))
    warning('Producer did not stop in time, killing it.');
    proc.Kill();
end
disp('actiCHamp producer stopped.');
end
