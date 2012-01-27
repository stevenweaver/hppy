
from multiprocessing import cpu_count, current_process
from os.path import abspath, exists
from textwrap import dedent

from fakemp import farmout, farmworker

from ._hyphyinterface import HyphyInterface, escape


__all__ = ['HyphyMap', 'mpi_node_count']


def mpi_node_count():
    iface = HyphyInterface()
    iface.queuecmd(dedent('''
    function _THyPhyAskFor( key ) {
        if ( key == "MPI" ) {
            return MPI_NODE_COUNT 
        }
        return "_THyPhy_NOT_HANDLED_";
    }'''))
    iface.runqueue()
    return int(iface.getvar('MPI', HyphyInterface.NUMBER))


class HyphyMap(object):

    def __init__(self, batchfile, retvar):
        if not exists(batchfile):
            raise ValueError('need to provide a real template batchfile!')
        self._batchfile = abspath(batchfile)
        self._retvar = retvar

    def map(self, argslist):
        node_count = mpi_node_count()
        numjobs = len(argslist)
        if node_count:
            # multiprocessing
            iface = HyphyInterface()
            cmd = dedent('''\
            _job = 0;
            _jobopts = {};
            %(jobopts)
            _jobvals = {};
            _nodestates = { MPI_NODE_COUNT-1, 2 };
            _received = 0;
            while ( _received < %(numjobs)d ) {
                if ( _job < %(numjobs)d ) {
                    for ( _node = 0; _node < MPI_NODE_COUNT-1; _node += 1 ) {
                        if ( _nodestates[ _node ][ 0 ] == 0 ) {
                            break;
                        }
                    }
                    _mpicmds = "";
                    _mpicmds * 128;
                    _mpicmds * ( "_options = " + _jobopts[ _job ] + ";" );
                    _mpicmds * ( "ExecuteAFile( %(batchfile)s );" );
                    _mpicmds * ( "_retstr = \"\";" );
                    _mpicmds * ( "_retstr * 128;" );
                    _mpicmds * ( "_retstr * ( \"_retjob = \" + " + _job + " + \";\" );" );
                    _mpicmds * ( "_retstr * ( \"_retval = \" + %(retvar)s + \";\" );" );
                    _mpicmds * ( "_retstr * 0;" );
                    _mpicmds * ( "return _retstr;" );
                    _mpicmds * 0;
                    MPISend( _node + 1, _mpicmds );
                    _nodestates[ _node ][ 0 ] = 1;
                    _nodestates[ _node ][ 1 ] = Time(0);
                    _job += 1;
                } else {
                    _node = ReceiveJobs( 0 );
                    _jobvals[ _retjob ] = _retval;
                    _received += 1;
                }
            }
            function _THyPhyAskFor( key ) {
                %(thyphyexprs)s
                return "_THyPhy_NOT_HANDLED_";
            }
            ''') % {
                'batchfile': escape(self._batchfile),
                'jobopts': '\n'.join('_jobopts[ %d ] = { %s };' % (
                    i,
                    ', '.join('%s: %s' % (escape(j), escape(v)) for j, v in enumerate(args))
                ) for i, args in enumerate(argslist)),
                'numjobs': numjobs,
                'retvar': self._retvar,
                'typhyexprs': '\n    '.join(dedent('''\
                    if ( key == "val%(jobid)d" ) {
                            return _jobvals[ %(jobid)d ];
                        }''') % {
                    'jobid': i
                } for i in range(numjobs))
            }
            iface.queuecmd(cmd)
            iface.runqueue()
            return [ iface.getvar("val%d" % i, HyphyInterface.STRING) for i in range(numjobs) ]
        else:
            # fork using multiprocessing
            pass
