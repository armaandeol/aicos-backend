import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import MainLayout from "../../components/erp/teacher/MainLayout";
import Card from "../../components/erp/teacher/Card";
import Select from "../../components/erp/teacher/Select";

const studentRoster = [
  { id: 1, initials: 'AJ', name: 'Alex Johnson', major: 'Physics Major', roll: '#PH-2024-001', color: 'blue', status: 'P', remark: '' },
  { id: 2, initials: 'BC', name: 'Beatrix Carter', major: 'Astrophysics Minor', roll: '#PH-2024-042', color: 'purple', status: 'A', remark: 'Medical Leave' },
  { id: 3, initials: 'DW', name: 'Damian Wayne', major: 'Physics Major', roll: '#PH-2024-019', color: 'amber', status: 'P', remark: '' },
  { id: 4, initials: 'ES', name: 'Eleanor Shellstrop', major: 'Quantum Computing', roll: '#PH-2024-088', color: 'blue', status: 'P', remark: '' },
  { id: 5, initials: 'FK', name: 'Franklin Knight', major: 'Physics Major', roll: '#PH-2024-102', color: 'slate', status: 'P', remark: '' },
];

const MarkAttendance = () => {
  const [students, setStudents] = useState(studentRoster);

  const updateStatus = (id, newStatus) => {
    setStudents(students.map(s => s.id === id ? { ...s, status: newStatus } : s));
  };

  const markAllPresent = () => {
    setStudents(students.map(s => ({ ...s, status: 'P' })));
  };

  const presentCount = students.filter(s => s.status === 'P').length;
  const absentCount = students.filter(s => s.status === 'A').length;
  const lateCount = students.filter(s => s.status === 'L').length;
  const successRate = Math.round((presentCount / students.length) * 100);

  return (
    <MainLayout title="Teacher Portal">
        <Link
to="/teacher/attendance"
className="flex items-center gap-2 text-primary font-semibold text-sm mb-4 hover:-translate-x-1 transition-transform w-max"
>

<span className="material-symbols-outlined">
arrow_back
</span>

Back to Attendance

</Link>
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
        <div className="flex items-center space-x-4">
        
          <div>
            <h2 className="text-3xl font-extrabold font-display text-blue-900 tracking-tight">Mark Attendance</h2>
            <p className="text-on-surface-variant font-medium">Attendance Overview • Today, Oct 24, 2023</p>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <button onClick={markAllPresent} className="px-5 py-2.5 rounded-xl bg-surface-container-high text-primary font-bold text-sm transition-all hover:bg-surface-container-highest active:scale-95">
            Mark All Present
          </button>
          <button className="px-6 py-2.5 rounded-xl bg-gradient-to-br from-primary to-primary-container text-white font-bold text-sm shadow-lg shadow-blue-500/20 hover:shadow-xl hover:shadow-blue-500/30 transition-all active:scale-95">
            Submit Attendance
          </button>
        </div>
      </div>

      {/* Dashboard Layout (Asymmetric Grid) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-16">
        
        {/* Left: Filters and Summary */}
        <div className="col-span-1 lg:col-span-4 space-y-8">
          {/* Summary Card (Glassmorphism) */}
          <div className="bg-gradient-to-br from-primary to-[#004395] rounded-3xl p-8 text-white relative overflow-hidden shadow-xl shadow-blue-900/10">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16 blur-2xl"></div>
            <div className="relative z-10">
              <h3 className="text-white/80 font-semibold mb-6">Attendance Summary</h3>
              <div className="flex justify-between items-end mb-8">
                <div>
                  <p className="text-5xl font-extrabold font-display">{students.length}</p>
                  <p className="text-sm text-white/70 mt-1">Total Students</p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold font-display">{successRate}%</p>
                  <p className="text-sm text-white/70 mt-1">Success Rate</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 pt-6 border-t border-white/10">
                <div>
                  <p className="text-xl font-bold">{presentCount}</p>
                  <p className="text-[10px] uppercase tracking-wider text-white/60">Present</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-red-200">{absentCount}</p>
                  <p className="text-[10px] uppercase tracking-wider text-white/60">Absent</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-orange-200">{lateCount}</p>
                  <p className="text-[10px] uppercase tracking-wider text-white/60">Late</p>
                </div>
              </div>
            </div>
          </div>

          {/* Filter Card */}
          <Card className="rounded-3xl p-8">
            <h4 className="text-blue-900 font-bold mb-6 flex items-center">
              <span className="material-symbols-outlined mr-2 text-primary">filter_list</span>
              Session Parameters
            </h4>
            <div className="space-y-5">
              <Select label="Class Name" options={['Advanced Quantum Physics', 'Classical Mechanics', 'Thermodynamics 101']} />
              <div className="grid grid-cols-2 gap-4">
                <Select label="Section" options={['Section A-1', 'Section A-2']} />
                <div>
                  <label className="text-xs font-bold text-on-surface-variant uppercase tracking-widest block mb-2">Date</label>
                  <div className="relative">
                    <input className="w-full bg-surface-container-low border-none rounded-xl px-4 py-3 text-sm font-medium focus:ring-2 focus:ring-primary/20 transition-all outline-none" type="date" defaultValue="2023-10-24" />
                  </div>
                </div>
              </div>
              <div className="pt-4">
                <button className="w-full py-3 bg-[#6b38d4]/10 text-[#6b38d4] font-bold rounded-xl hover:bg-[#6b38d4]/20 transition-all text-sm">
                  Update View
                </button>
              </div>
            </div>
          </Card>

          {/* AI Insights (Tertiary Accent) */}
          <div className="bg-orange-50 rounded-3xl p-6 relative overflow-hidden border border-amber-900/10">
            <div className="flex items-start space-x-4">
              <div className="bg-amber-700 text-white p-2 rounded-lg flex items-center justify-center">
                <span className="material-symbols-outlined text-xl">auto_awesome</span>
              </div>
              <div className="relative z-10">
                <h5 className="text-amber-900 font-bold text-sm">Attendance Insight</h5>
                <p className="text-amber-800 text-xs mt-1 leading-relaxed">
                  Marcus and Sophia have been late for the last 3 sessions of this class. Consider checking in with them.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Student Roster */}
        <div className="col-span-1 lg:col-span-8">
          <div className="bg-surface-container-lowest rounded-3xl shadow-[0px_12px_32px_rgba(11,28,48,0.04)] overflow-hidden border border-outline-variant/10">
            {/* Table Header */}
            <div className="px-8 py-6 bg-surface-container-low flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
              <h3 className="font-display font-bold text-blue-900">Student Roster</h3>
              <div className="flex items-center space-x-4 text-xs font-bold text-on-surface-variant uppercase tracking-widest">
                <span>Status Key:</span>
                <div className="flex items-center space-x-4">
                  <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-green-500 mr-1"></span> P</span>
                  <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-red-500 mr-1"></span> A</span>
                  <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-orange-500 mr-1"></span> L</span>
                </div>
              </div>
            </div>

            {/* Table Body */}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px]">
                <thead>
                  <tr className="text-left text-on-surface-variant border-b border-surface-container">
                    <th className="px-8 py-4 text-[11px] font-bold uppercase tracking-widest">Student</th>
                    <th className="px-4 py-4 text-[11px] font-bold uppercase tracking-widest">Roll No.</th>
                    <th className="px-4 py-4 text-[11px] font-bold uppercase tracking-widest text-center">Attendance Action</th>
                    <th className="px-8 py-4 text-[11px] font-bold uppercase tracking-widest text-right">Remarks</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container/50">
                  {students.map((student) => (
                    <tr key={student.id} className="hover:bg-surface-container-low transition-colors group">
                      <td className="px-8 py-5">
                        <div className="flex items-center space-x-3">
                          <div className={`w-10 h-10 rounded-full bg-${student.color}-100 flex items-center justify-center text-${student.color === 'slate' ? 'slate' : 'primary'} font-bold`}>
                            {student.initials}
                          </div>
                          <div>
                            <p className="text-sm font-bold text-on-surface">{student.name}</p>
                            <p className="text-xs text-on-surface-variant">{student.major}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-5 text-sm font-medium text-on-surface-variant">{student.roll}</td>
                      <td className="px-4 py-5">
                        <div className="flex items-center justify-center space-x-2">
                          <button 
                            onClick={() => updateStatus(student.id, 'P')}
                            className={`w-12 py-2 rounded-lg font-bold text-xs transition-all ${student.status === 'P' ? 'bg-green-500 text-white shadow-md shadow-green-500/20' : 'bg-surface-container-high text-on-surface-variant hover:bg-green-50'}`}
                          >P</button>
                          <button 
                            onClick={() => updateStatus(student.id, 'A')}
                            className={`w-12 py-2 rounded-lg font-bold text-xs transition-all ${student.status === 'A' ? 'bg-red-500 text-white shadow-md shadow-red-500/20' : 'bg-surface-container-high text-on-surface-variant hover:bg-red-50'}`}
                          >A</button>
                          <button 
                            onClick={() => updateStatus(student.id, 'L')}
                            className={`w-12 py-2 rounded-lg font-bold text-xs transition-all ${student.status === 'L' ? 'bg-orange-500 text-white shadow-md shadow-orange-500/20' : 'bg-surface-container-high text-on-surface-variant hover:bg-orange-50'}`}
                          >L</button>
                        </div>
                      </td>
                      <td className="px-8 py-5 text-right flex justify-end">
                        {student.remark ? (
                          <span className="text-[10px] bg-red-50 text-red-600 px-2 py-1 rounded-md font-bold uppercase tracking-tighter inline-block">
                            {student.remark}
                          </span>
                        ) : (
                          <button className="p-2 rounded-lg text-slate-300 hover:text-primary transition-colors">
                            <span className="material-symbols-outlined">add_comment</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Table Footer / Pagination */}
            <div className="px-8 py-4 bg-surface-container-lowest border-t border-slate-100 flex justify-between items-center text-sm font-medium text-on-surface-variant">
              <span>Showing 5 of {students.length} students</span>
              <div className="flex space-x-2">
                <button className="px-3 py-1.5 rounded-lg bg-surface-container-low hover:bg-surface-container text-primary transition-colors">1</button>
                <button className="px-3 py-1.5 rounded-lg hover:bg-surface-container transition-colors disabled:opacity-50" disabled>2</button>
                <button className="px-3 py-1.5 rounded-lg hover:bg-surface-container transition-colors disabled:opacity-50" disabled>3</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

export default MarkAttendance;
